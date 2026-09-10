"""Scheduled expiry evidence for delayed payments without confirmation."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import Currency, DelayedPaymentDecision
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    PaymentRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services import confirmations
from payment_quality_lab.services.confirmations import (
    ConfirmationCommand,
    expire_due_payments,
    process_confirmation,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
)

BASE_TIME = datetime(2026, 9, 10, 1, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with create_session_factory(engine)() as database_session:
        yield database_session
    engine.dispose()


def create_delayed_payment(
    session: Session,
    *,
    sequence: int,
    created_at: datetime = BASE_TIME,
) -> PaymentRecord:
    outcome = authorize_payment(
        session,
        command=AuthorizationCommand(
            merchant_reference=f"scheduled-expiry-order-{sequence}",
            amount=2500,
            currency=Currency.JPY,
            payment_method_token=DelayedPaymentDecision.AWAIT_CONFIRMATION,
        ),
        idempotency_key=f"scheduled-expiry-key-{sequence}",
        clock=lambda: created_at,
    )
    assert isinstance(outcome.payment, PaymentRecord)
    return outcome.payment


def event_types(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(WebhookEventRecord.event_type).order_by(
                WebhookEventRecord.created_at,
                WebhookEventRecord.aggregate_version,
            )
        )
    )


def test_conf_03_payment_is_not_expired_before_its_deadline(
    session: Session,
) -> None:
    payment = create_delayed_payment(session, sequence=1)

    result = expire_due_payments(
        session,
        now=BASE_TIME + timedelta(hours=72) - timedelta(microseconds=1),
    )

    stored = session.get(PaymentRecord, payment.id)
    assert result.expired_count == 0
    assert result.expired_payment_ids == ()
    assert stored is not None
    assert stored.status == "AWAITING_PAYMENT"
    assert stored.version == 1
    assert event_types(session) == ["payment.confirmation_requested"]


@pytest.mark.parametrize("elapsed", [timedelta(hours=72), timedelta(hours=80)])
def test_conf_03_payment_expires_at_or_after_its_deadline(
    session: Session,
    elapsed: timedelta,
) -> None:
    payment = create_delayed_payment(session, sequence=1)

    result = expire_due_payments(session, now=BASE_TIME + elapsed)

    stored = session.get(PaymentRecord, payment.id)
    assert result.expired_payment_ids == (payment.id,)
    assert result.expired_count == 1
    assert stored is not None
    assert stored.status == "EXPIRED"
    assert stored.updated_at.replace(tzinfo=UTC) == BASE_TIME + elapsed
    assert stored.authorized_amount == 0
    assert stored.captured_amount == 0
    assert stored.refunded_amount == 0
    assert stored.version == 2
    assert session.scalar(select(func.count()).select_from(LedgerEntryRecord)) == 0
    assert event_types(session) == [
        "payment.confirmation_requested",
        "payment.expired",
    ]


def test_conf_03_repeated_run_creates_no_second_expiry_effect(
    session: Session,
) -> None:
    payment = create_delayed_payment(session, sequence=1)
    deadline = BASE_TIME + timedelta(hours=72)

    first = expire_due_payments(session, now=deadline)
    second = expire_due_payments(session, now=deadline + timedelta(hours=1))

    stored = session.get(PaymentRecord, payment.id)
    assert first.expired_payment_ids == (payment.id,)
    assert second.expired_payment_ids == ()
    assert stored is not None
    assert stored.status == "EXPIRED"
    assert stored.version == 2
    assert event_types(session).count("payment.expired") == 1


def test_conf_03_bounded_batch_uses_deterministic_expiry_order(
    session: Session,
) -> None:
    earliest = create_delayed_payment(
        session,
        sequence=1,
        created_at=BASE_TIME - timedelta(hours=3),
    )
    middle = create_delayed_payment(
        session,
        sequence=2,
        created_at=BASE_TIME - timedelta(hours=2),
    )
    latest_due = create_delayed_payment(
        session,
        sequence=3,
        created_at=BASE_TIME - timedelta(hours=1),
    )
    future = create_delayed_payment(
        session,
        sequence=4,
        created_at=BASE_TIME + timedelta(hours=1),
    )
    now = BASE_TIME + timedelta(hours=72)

    first = expire_due_payments(session, now=now, limit=2)
    second = expire_due_payments(session, now=now, limit=2)

    assert first.expired_payment_ids == (earliest.id, middle.id)
    assert second.expired_payment_ids == (latest_due.id,)
    assert session.get(PaymentRecord, future.id).status == "AWAITING_PAYMENT"
    assert event_types(session).count("payment.expired") == 3
    assert session.scalar(select(func.count()).select_from(LedgerEntryRecord)) == 0


def test_conf_03_resolved_payment_is_not_selected(
    session: Session,
) -> None:
    payment = create_delayed_payment(session, sequence=1)
    assert payment.payment_reference is not None
    process_confirmation(
        session,
        command=ConfirmationCommand(
            confirmation_id="cnf_scheduled_expiry_captured",
            payment_reference=payment.payment_reference,
            amount=payment.amount,
            currency=Currency(payment.currency),
        ),
        received_at=BASE_TIME + timedelta(hours=1),
    )

    result = expire_due_payments(
        session,
        now=BASE_TIME + timedelta(hours=80),
    )

    stored = session.get(PaymentRecord, payment.id)
    assert result.expired_count == 0
    assert stored is not None
    assert stored.status == "CAPTURED"
    assert stored.version == 2
    assert event_types(session) == [
        "payment.confirmation_requested",
        "payment.captured",
    ]


def test_conf_03_event_failure_rolls_back_the_complete_bounded_batch(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = create_delayed_payment(session, sequence=1)
    second = create_delayed_payment(session, sequence=2)
    original_create_event = confirmations.create_outbox_event
    calls = 0

    def fail_second_event(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated second expiry event failure")
        return original_create_event(*args, **kwargs)

    monkeypatch.setattr(confirmations, "create_outbox_event", fail_second_event)

    with pytest.raises(RuntimeError, match="second expiry event failure"):
        expire_due_payments(session, now=BASE_TIME + timedelta(hours=72))

    session.expire_all()
    assert session.get(PaymentRecord, first.id).status == "AWAITING_PAYMENT"
    assert session.get(PaymentRecord, second.id).status == "AWAITING_PAYMENT"
    assert event_types(session).count("payment.expired") == 0
    assert session.scalar(select(func.count()).select_from(LedgerEntryRecord)) == 0


@pytest.mark.parametrize("limit", [0, 1_001])
def test_conf_03_rejects_an_invalid_batch_limit(
    session: Session,
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        expire_due_payments(session, now=BASE_TIME, limit=limit)


def test_conf_03_rejects_a_naive_scheduler_time(session: Session) -> None:
    with pytest.raises(ValueError, match="now must be a timezone-aware datetime"):
        expire_due_payments(session, now=datetime(2026, 9, 10, 1, 0))
