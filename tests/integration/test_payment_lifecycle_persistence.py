"""Persistence integration tests for payment lifecycle transactions."""

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    InvalidPaymentTransitionError,
)
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
    cancel_payment,
    capture_payment,
    get_ledger_entries,
    refund_payment,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = create_session_factory(engine)
    with factory() as database_session:
        yield database_session
    engine.dispose()


def authorize_approved(session: Session) -> PaymentRecord:
    return authorize_payment(
        session,
        command=AuthorizationCommand(
            merchant_reference="lifecycle-integration-order",
            amount=1000,
            currency=Currency.JPY,
            payment_method_token=AuthorizationDecision.APPROVE,
        ),
        idempotency_key="integration-authorize-lifecycle",
    ).payment


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_full_lifecycle_commits_each_effect_and_idempotency_record(
    session: Session,
) -> None:
    payment = authorize_approved(session)

    captured = capture_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-capture-lifecycle",
    ).payment
    partial = refund_payment(
        session,
        payment_id=payment.id,
        amount=400,
        idempotency_key="integration-refund-partial",
    ).payment
    refunded = refund_payment(
        session,
        payment_id=payment.id,
        amount=600,
        idempotency_key="integration-refund-remaining",
    ).payment

    assert captured.id == partial.id == refunded.id == payment.id
    assert refunded.status == "REFUNDED"
    assert refunded.authorized_amount == 1000
    assert refunded.captured_amount == 1000
    assert refunded.refunded_amount == 1000
    assert refunded.version == 4
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 4
    assert count(session, IdempotencyRecord) == 4
    assert [entry.operation for entry in get_ledger_entries(session, payment.id)] == [
        "AUTHORIZATION",
        "CAPTURE",
        "REFUND",
        "REFUND",
    ]


def test_cancellation_commits_reversal_without_capture(session: Session) -> None:
    payment = authorize_approved(session)

    outcome = cancel_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-cancel-lifecycle",
    )

    assert outcome.payment.status == "CANCELLED"
    assert outcome.payment.captured_amount == 0
    assert outcome.payment.version == 2
    entries = get_ledger_entries(session, payment.id)
    assert [(entry.operation, entry.amount) for entry in entries] == [
        ("AUTHORIZATION", 1000),
        ("CANCEL", 1000),
    ]


def test_invalid_transition_leaves_all_persisted_state_unchanged(
    session: Session,
) -> None:
    payment = authorize_approved(session)
    captured = capture_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-capture-once",
    ).payment
    expected_updated_at = captured.updated_at

    with pytest.raises(InvalidPaymentTransitionError):
        capture_payment(
            session,
            payment_id=payment.id,
            idempotency_key="integration-capture-invalid",
        )

    session.expire_all()
    unchanged = session.get(PaymentRecord, payment.id)
    assert unchanged is not None
    assert unchanged.status == "CAPTURED"
    assert unchanged.version == 2
    assert unchanged.updated_at.replace(tzinfo=expected_updated_at.tzinfo) == (
        expected_updated_at
    )
    assert count(session, LedgerEntryRecord) == 2
    assert count(session, IdempotencyRecord) == 2


def test_idempotent_capture_replay_adds_no_financial_effect(
    session: Session,
) -> None:
    payment = authorize_approved(session)

    first = capture_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-capture-replay",
    )
    replay = capture_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-capture-replay",
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.payment.id == first.payment.id
    assert replay.payment.version == 2
    assert count(session, LedgerEntryRecord) == 2
    assert count(session, IdempotencyRecord) == 2


def test_database_constraint_rejects_captured_amount_above_authorization(
    session: Session,
) -> None:
    payment = authorize_approved(session)
    payment.captured_amount = payment.authorized_amount + 1

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.refresh(payment)
    assert payment.captured_amount == 0
    assert payment.status == "AUTHORIZED"


def test_database_constraint_rejects_refund_above_capture(session: Session) -> None:
    payment = authorize_approved(session)
    captured = capture_payment(
        session,
        payment_id=payment.id,
        idempotency_key="integration-capture-constraint",
    ).payment
    captured.refunded_amount = captured.captured_amount + 1

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.refresh(captured)
    assert captured.refunded_amount == 0
    assert captured.status == "CAPTURED"
