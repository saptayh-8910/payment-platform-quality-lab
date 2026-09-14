"""Reliability tests for concurrent requests and ambiguous outcomes."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import AuthorizationDecision, Currency
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
    ConcurrentPaymentUpdateError,
    FailurePoint,
    PaymentSnapshot,
    SimulatedPaymentTimeoutError,
    authorize_payment,
    cancel_payment,
    capture_payment,
    get_ledger_entries,
    refund_payment,
)


@pytest.fixture
def factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    """Provide independent sessions over one file-backed SQLite database."""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'reliability.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def command() -> AuthorizationCommand:
    return AuthorizationCommand(
        merchant_reference="reliability-order",
        amount=1000,
        currency=Currency.JPY,
        payment_method_token=AuthorizationDecision.APPROVE,
    )


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def authorize_once(
    factory: sessionmaker[Session],
    command: AuthorizationCommand,
    *,
    key: str = "reliability-authorize",
) -> str:
    with factory() as session:
        return authorize_payment(
            session,
            command=command,
            idempotency_key=key,
        ).payment.id


def test_concurrent_equivalent_authorizations_create_one_financial_effect(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    barrier = Barrier(2)

    def submit() -> tuple[str, bool, int]:
        with factory() as session:
            barrier.wait()
            outcome = authorize_payment(
                session,
                command=command,
                idempotency_key="concurrent-authorization-key",
            )
            return outcome.payment.id, outcome.replayed, outcome.payment.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert len({payment_id for payment_id, _, _ in outcomes}) == 1
    assert sorted(replayed for _, replayed, _ in outcomes) == [False, True]
    assert {version for _, _, version in outcomes} == {1}
    with factory() as session:
        assert count(session, PaymentRecord) == 1
        assert count(session, LedgerEntryRecord) == 1
        assert count(session, IdempotencyRecord) == 1


def test_concurrent_equivalent_captures_increment_version_once(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    barrier = Barrier(2)

    def submit() -> tuple[bool, int]:
        with factory() as session:
            barrier.wait()
            outcome = capture_payment(
                session,
                payment_id=payment_id,
                idempotency_key="concurrent-capture-key",
            )
            return outcome.replayed, outcome.payment.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert sorted(replayed for replayed, _ in outcomes) == [False, True]
    assert {version for _, version in outcomes} == {2}
    with factory() as session:
        payment = session.get(PaymentRecord, payment_id)
        assert payment is not None
        assert payment.status == "CAPTURED"
        assert payment.version == 2
        assert count(session, LedgerEntryRecord) == 2
        assert count(session, IdempotencyRecord) == 2


def test_concurrent_equivalent_refunds_create_one_refund_entry(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="capture-before-concurrent-refund",
        )
    barrier = Barrier(2)

    def submit() -> tuple[bool, int]:
        with factory() as session:
            barrier.wait()
            outcome = refund_payment(
                session,
                payment_id=payment_id,
                amount=400,
                idempotency_key="concurrent-refund-key",
            )
            return outcome.replayed, outcome.payment.refunded_amount

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert sorted(replayed for replayed, _ in outcomes) == [False, True]
    assert {amount for _, amount in outcomes} == {400}
    with factory() as session:
        payment = session.get(PaymentRecord, payment_id)
        assert payment is not None
        assert payment.refunded_amount == 400
        refund_entries = [
            entry
            for entry in get_ledger_entries(session, payment_id)
            if entry.operation == "REFUND"
        ]
        assert [(entry.amount, entry.currency) for entry in refund_entries] == [
            (400, "JPY")
        ]


def test_optimistic_lock_rejects_stale_competing_transition(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    winner = factory()
    stale = factory()
    try:
        stale_payment = stale.get(PaymentRecord, payment_id)
        assert stale_payment is not None
        stale.commit()
        cancel_payment(
            winner,
            payment_id=payment_id,
            idempotency_key="winning-cancellation-key",
        )

        with pytest.raises(ConcurrentPaymentUpdateError):
            capture_payment(
                stale,
                payment_id=payment_id,
                idempotency_key="stale-capture-key",
            )
    finally:
        winner.close()
        stale.close()

    with factory() as session:
        payment = session.get(PaymentRecord, payment_id)
        assert payment is not None
        assert (payment.status, payment.version) == ("CANCELLED", 2)
        assert [
            entry.operation for entry in get_ledger_entries(session, payment_id)
        ] == ["AUTHORIZATION", "CANCEL"]
        assert count(session, IdempotencyRecord) == 2


def test_competing_refunds_cannot_exceed_captured_amount(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="capture-before-competing-refunds",
        )

    winner = factory()
    stale = factory()
    try:
        stale_payment = stale.get(PaymentRecord, payment_id)
        assert stale_payment is not None
        stale.commit()
        refund_payment(
            winner,
            payment_id=payment_id,
            amount=700,
            idempotency_key="winning-refund-key",
        )

        with pytest.raises(ConcurrentPaymentUpdateError):
            refund_payment(
                stale,
                payment_id=payment_id,
                amount=600,
                idempotency_key="stale-refund-key",
            )
    finally:
        winner.close()
        stale.close()

    with factory() as session:
        payment = session.get(PaymentRecord, payment_id)
        assert payment is not None
        assert payment.refunded_amount == 700
        assert payment.refunded_amount <= payment.captured_amount
        refunds = [
            entry.amount
            for entry in get_ledger_entries(session, payment_id)
            if entry.operation == "REFUND"
        ]
        assert refunds == [700]
        assert count(session, IdempotencyRecord) == 3


def test_original_authorization_snapshot_survives_later_state_changes(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    key = "immutable-authorization-response"
    payment_id = authorize_once(factory, command, key=key)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="capture-after-authorization-response",
        )
        replay = authorize_payment(session, command=command, idempotency_key=key)
        current = session.get(PaymentRecord, payment_id)

    assert replay.replayed is True
    assert isinstance(replay.payment, PaymentSnapshot)
    assert (replay.payment.status, replay.payment.version) == ("AUTHORIZED", 1)
    assert current is not None
    assert (current.status, current.version) == ("CAPTURED", 2)


def test_timeout_before_commit_rolls_back_and_retry_succeeds_fresh(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    key = "timeout-before-commit-key"
    with factory() as session:
        with pytest.raises(SimulatedPaymentTimeoutError) as timeout:
            authorize_payment(
                session,
                command=command,
                idempotency_key=key,
                failure_point=FailurePoint.BEFORE_COMMIT,
            )
        assert timeout.value.point is FailurePoint.BEFORE_COMMIT
        assert count(session, PaymentRecord) == 0
        assert count(session, LedgerEntryRecord) == 0
        assert count(session, IdempotencyRecord) == 0

        retry = authorize_payment(session, command=command, idempotency_key=key)

    assert retry.replayed is False
    assert retry.payment.status == "AUTHORIZED"


def test_invalid_authorization_rolls_back_its_idempotency_claim(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    invalid = AuthorizationCommand(
        merchant_reference=command.merchant_reference,
        amount=0,
        currency=command.currency,
        payment_method_token=command.payment_method_token,
    )
    with factory() as session:
        with pytest.raises(ValueError, match="Payment amount must be positive"):
            authorize_payment(
                session,
                command=invalid,
                idempotency_key="invalid-authorization-claim",
            )

        assert count(session, PaymentRecord) == 0
        assert count(session, LedgerEntryRecord) == 0
        assert count(session, IdempotencyRecord) == 0


def test_timeout_after_commit_retries_original_result_without_duplicate(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    key = "timeout-after-commit-key"
    with factory() as session:
        with pytest.raises(SimulatedPaymentTimeoutError) as timeout:
            authorize_payment(
                session,
                command=command,
                idempotency_key=key,
                failure_point=FailurePoint.AFTER_COMMIT,
            )
        assert timeout.value.point is FailurePoint.AFTER_COMMIT

    with factory() as session:
        retry = authorize_payment(session, command=command, idempotency_key=key)
        assert retry.replayed is True
        assert retry.payment.status == "AUTHORIZED"
        assert count(session, PaymentRecord) == 1
        assert count(session, LedgerEntryRecord) == 1
        assert count(session, IdempotencyRecord) == 1


def test_ledger_totals_match_payment_after_recovered_refund_timeout(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="ledger-consistency-capture",
        )
        with pytest.raises(SimulatedPaymentTimeoutError):
            refund_payment(
                session,
                payment_id=payment_id,
                amount=350,
                idempotency_key="ledger-consistency-refund",
                failure_point=FailurePoint.AFTER_COMMIT,
            )

    with factory() as session:
        retry = refund_payment(
            session,
            payment_id=payment_id,
            amount=350,
            idempotency_key="ledger-consistency-refund",
        )
        payment = session.get(PaymentRecord, payment_id)
        entries = get_ledger_entries(session, payment_id)

    assert retry.replayed is True
    assert payment is not None
    assert sum(e.amount for e in entries if e.operation == "AUTHORIZATION") == (
        payment.authorized_amount
    )
    assert sum(e.amount for e in entries if e.operation == "CAPTURE") == (
        payment.captured_amount
    )
    assert sum(e.amount for e in entries if e.operation == "REFUND") == (
        payment.refunded_amount
    )
