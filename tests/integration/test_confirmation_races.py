"""RACE-01: real connections, explicit checkpoints, and restartable receipts."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event, current_thread

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError

from payment_quality_lab.domain.payment import Currency, DelayedPaymentDecision
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    ConfirmationReceiptRecord,
    LedgerEntryRecord,
    PaymentConfirmationRecord,
    PaymentRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services import confirmations as service
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
)

CREATED = datetime(2026, 9, 11, tzinfo=UTC)
DEADLINE = CREATED + timedelta(hours=72)
ON_TIME = DEADLINE - timedelta(seconds=1)


@pytest.fixture
def lab(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        payment = authorize_payment(
            session,
            command=AuthorizationCommand(
                merchant_reference="race-order",
                amount=2500,
                currency=Currency.JPY,
                payment_method_token=DelayedPaymentDecision.AWAIT_CONFIRMATION,
            ),
            idempotency_key="race-create-key",
            clock=lambda: CREATED,
        ).payment
        command = service.ConfirmationCommand(
            "cnf_race", payment.payment_reference, 2500, Currency.JPY
        )
        payment_id = payment.id
    yield engine, factory, command, payment_id
    engine.dispose()


def invoke(lab, function, *args, **kwargs):
    with lab[1]() as session:
        return function(session, *args, **kwargs)


def assert_result(lab, state, *, receipts=1, dispositions=None):
    with lab[1]() as session:
        payment = session.get(PaymentRecord, lab[3])
        assert payment.status == state
        assert payment.version == 2
        expected_amount = 2500 if state == "CAPTURED" else 0
        assert payment.authorized_amount == payment.captured_amount == expected_amount
        assert payment.refunded_amount == 0
        ledger = list(session.scalars(select(LedgerEntryRecord)))
        assert [(row.operation, row.amount) for row in ledger] == (
            [("CONFIRMATION_CAPTURE", 2500)] if expected_amount else []
        )
        events = list(
            session.scalars(
                select(WebhookEventRecord).order_by(
                    WebhookEventRecord.aggregate_version
                )
            )
        )
        assert [(row.event_type, row.aggregate_version) for row in events] == [
            ("payment.confirmation_requested", 1),
            ("payment.captured" if expected_amount else "payment.expired", 2),
        ]
        stored = list(session.scalars(select(ConfirmationReceiptRecord)))
        assert len(stored) == receipts
        assert all(row.completed for row in stored)
        if dispositions is not None:
            assert sorted(
                session.scalars(select(PaymentConfirmationRecord.disposition))
            ) == sorted(dispositions)


@pytest.mark.parametrize("expiry_first", [True, False])
def test_a_b_committed_receipt_survives_paused_processing(lab, expiry_first):
    committed, resume = Event(), Event()

    def sender():
        invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)
        committed.set()
        assert resume.wait(5)
        return invoke(lab, service.complete_confirmation, lab[2].confirmation_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(sender)
        try:
            assert committed.wait(5)
            # Observe durability from another physical connection before expiry.
            with lab[1]() as session:
                receipt = session.get(ConfirmationReceiptRecord, lab[2].confirmation_id)
                assert receipt is not None and not receipt.completed
                assert session.get(PaymentRecord, lab[3]).status == "AWAITING_PAYMENT"
            if expiry_first:
                assert (
                    invoke(lab, service.expire_due_payments, now=DEADLINE).expired_count
                    == 0
                )
            resume.set()
            future.result(timeout=5)
            assert (
                invoke(lab, service.expire_due_payments, now=DEADLINE).expired_count
                == 0
            )
        finally:
            resume.set()
    assert_result(lab, "CAPTURED", dispositions=["applied"])


def test_c_no_receipt_expires(lab):
    assert invoke(lab, service.expire_due_payments, now=DEADLINE).expired_count == 1
    assert_result(lab, "EXPIRED", receipts=0, dispositions=[])


@pytest.mark.parametrize("accepted", [DEADLINE, DEADLINE + timedelta(seconds=1)])
@pytest.mark.parametrize("expiry_first", [True, False])
def test_d_boundary_and_late_receipt_both_orders(lab, accepted, expiry_first):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: accepted)
    if expiry_first:
        invoke(lab, service.expire_due_payments, now=accepted)
    invoke(lab, service.complete_confirmation, lab[2].confirmation_id)
    invoke(lab, service.expire_due_payments, now=accepted)
    assert_result(lab, "EXPIRED", dispositions=["late"])


def contend(lab, monkeypatch, first, second, checkpoint, blocked_check=None):
    """Pause the owner inside its transaction and observe contender's BEGIN."""
    paused, release, attempting = Event(), Event(), Event()
    original = getattr(service, checkpoint)
    connections = set()

    def pause(*args, **kwargs):
        if current_thread().name.startswith("owner"):
            paused.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    def before_sql(connection, cursor, statement, parameters, context, executemany):
        if statement == "BEGIN IMMEDIATE":
            connections.add(id(connection.connection.driver_connection))
            if current_thread().name.startswith("contender"):
                attempting.set()

    monkeypatch.setattr(service, checkpoint, pause)
    event.listen(lab[0], "before_cursor_execute", before_sql)
    try:
        with (
            ThreadPoolExecutor(1, thread_name_prefix="owner") as a,
            ThreadPoolExecutor(1, thread_name_prefix="contender") as b,
        ):
            owner = a.submit(first)
            try:
                assert paused.wait(5)
                contender = b.submit(second)
                assert attempting.wait(5)
                assert not contender.done()
                if blocked_check is not None:
                    assert blocked_check()
            finally:
                release.set()
            result = owner.result(timeout=5), contender.result(timeout=5)
        assert len(connections) >= 2
        return result
    finally:
        event.remove(lab[0], "before_cursor_execute", before_sql)


def test_e_expiry_selected_before_acceptance_blocks_and_resamples_clock(
    lab, monkeypatch
):
    sampled = Event()

    def clock():
        sampled.set()
        return DEADLINE + timedelta(seconds=1)

    def accept():
        assert not sampled.is_set()
        return invoke(lab, service.process_confirmation, command=lab[2], clock=clock)

    contend(
        lab,
        monkeypatch,
        lambda: invoke(lab, service.expire_due_payments, now=DEADLINE),
        accept,
        "_apply_expiry_transition",
        blocked_check=lambda: not sampled.is_set(),
    )
    assert sampled.is_set()
    with lab[1]() as session:
        receipt = session.get(ConfirmationReceiptRecord, lab[2].confirmation_id)
        assert receipt.received_at.replace(tzinfo=UTC) > DEADLINE
    assert_result(lab, "EXPIRED", dispositions=["late"])


@pytest.mark.parametrize("recovery", [False, True])
def test_f_m_caller_retry_competes_with_completion_or_recovery(
    lab, monkeypatch, recovery
):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)
    owner = (
        (lambda: invoke(lab, service.recover_pending_confirmations))
        if recovery
        else (
            lambda: invoke(lab, service.complete_confirmation, lab[2].confirmation_id)
        )
    )
    _, retry = contend(
        lab,
        monkeypatch,
        owner,
        lambda: invoke(
            lab, service.process_confirmation, command=lab[2], clock=lambda: DEADLINE
        ),
        "_apply_disposition",
    )
    assert retry.replayed
    with lab[1]() as session:
        assert (
            session.get(
                ConfirmationReceiptRecord, lab[2].confirmation_id
            ).received_at.replace(tzinfo=UTC)
            == ON_TIME
        )
    assert_result(lab, "CAPTURED", dispositions=["applied"])


def test_g_conflicting_retry_does_not_replace_pending_receipt(lab):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)
    with pytest.raises(service.ConfirmationIdConflictError):
        invoke(
            lab,
            service.process_confirmation,
            command=replace(lab[2], amount=2501),
            clock=lambda: DEADLINE,
        )
    with lab[1]() as session:
        receipt = session.get(ConfirmationReceiptRecord, lab[2].confirmation_id)
        assert not receipt.completed and receipt.amount == 2500
        assert session.get(PaymentRecord, lab[3]).status == "AWAITING_PAYMENT"
    invoke(lab, service.recover_pending_confirmations)
    assert_result(lab, "CAPTURED", dispositions=["applied"])


def test_h_distinct_matching_confirmations_capture_once(lab, monkeypatch):
    second = replace(lab[2], confirmation_id="cnf_other")
    for command in (lab[2], second):
        invoke(lab, service.accept_confirmation, command=command, clock=lambda: ON_TIME)
    contend(
        lab,
        monkeypatch,
        lambda: invoke(lab, service.complete_confirmation, lab[2].confirmation_id),
        lambda: invoke(lab, service.complete_confirmation, second.confirmation_id),
        "_apply_disposition",
    )
    assert_result(
        lab, "CAPTURED", receipts=2, dispositions=["applied", "already_resolved"]
    )


def test_i_restart_recovery_uses_original_receipt_and_is_repeatable(lab):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)
    lab[0].dispose()
    assert invoke(lab, service.expire_due_payments, now=DEADLINE).expired_count == 0
    assert invoke(lab, service.recover_pending_confirmations) == (
        lab[2].confirmation_id,
    )
    assert invoke(lab, service.recover_pending_confirmations) == ()
    assert_result(lab, "CAPTURED", dispositions=["applied"])


def test_j_event_failure_leaves_recoverable_receipt(lab, monkeypatch):
    original = service.create_outbox_event

    def fail(*args, **kwargs):
        raise RuntimeError("injected event failure")

    monkeypatch.setattr(service, "create_outbox_event", fail)
    with pytest.raises(service.ConfirmationProcessingUnavailableError):
        invoke(lab, service.process_confirmation, command=lab[2], clock=lambda: ON_TIME)
    with lab[1]() as session:
        assert not session.get(
            ConfirmationReceiptRecord, lab[2].confirmation_id
        ).completed
        assert session.get(PaymentRecord, lab[3]).status == "AWAITING_PAYMENT"
        assert list(session.scalars(select(LedgerEntryRecord))) == []
        assert list(session.scalars(select(PaymentConfirmationRecord))) == []
        assert len(list(session.scalars(select(WebhookEventRecord)))) == 1
    monkeypatch.setattr(service, "create_outbox_event", original)
    invoke(lab, service.recover_pending_confirmations)
    assert_result(lab, "CAPTURED", dispositions=["applied"])


@pytest.mark.parametrize("changes", [{"amount": 2501}, {"currency": Currency.USD}])
def test_k_pending_mismatch_does_not_protect_expiry(lab, changes):
    invoke(
        lab,
        service.accept_confirmation,
        command=replace(lab[2], **changes),
        clock=lambda: ON_TIME,
    )
    assert invoke(lab, service.expire_due_payments, now=DEADLINE).expired_count == 1
    invoke(lab, service.recover_pending_confirmations)
    # Current final classification gives terminal EXPIRED precedence.
    assert_result(lab, "EXPIRED", dispositions=["late"])


def test_n_overlapping_expiry_sweeps_commit_one_effect(lab, monkeypatch):
    first, second = contend(
        lab,
        monkeypatch,
        lambda: invoke(lab, service.expire_due_payments, now=DEADLINE),
        lambda: invoke(lab, service.expire_due_payments, now=DEADLINE),
        "_apply_expiry_transition",
    )
    assert first.expired_count == 1 and second.expired_count == 0
    assert_result(lab, "EXPIRED", receipts=0, dispositions=[])


def test_late_confirmation_cannot_expire_an_on_time_pending_receipt(lab):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)
    invoke(
        lab,
        service.process_confirmation,
        command=replace(lab[2], confirmation_id="cnf_late"),
        clock=lambda: DEADLINE,
    )
    invoke(lab, service.recover_pending_confirmations)
    assert_result(lab, "CAPTURED", receipts=2, dispositions=["late", "applied"])


def test_upgrade_backfills_completed_receipts_without_reapplying_money(lab):
    from payment_quality_lab.persistence.migrations import upgrade_database

    invoke(lab, service.process_confirmation, command=lab[2], clock=lambda: ON_TIME)
    with lab[0].begin() as connection:
        before = connection.execute(text("SELECT * FROM payment_confirmations")).all()
        connection.execute(text("DROP TABLE confirmation_receipts"))
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('0004_confirmations')")
        )
    assert upgrade_database(str(lab[0].url)) == "0005_receipts"
    assert upgrade_database(str(lab[0].url)) == "0005_receipts"
    with lab[0].connect() as connection:
        assert (
            connection.execute(text("SELECT * FROM payment_confirmations")).all()
            == before
        )
    assert invoke(lab, service.recover_pending_confirmations) == ()
    assert invoke(
        lab, service.process_confirmation, command=lab[2], clock=lambda: DEADLINE
    ).replayed
    assert_result(lab, "CAPTURED", dispositions=["applied"])


def test_bounded_recovery_skips_completed_work(lab):
    for index in range(3):
        invoke(
            lab,
            service.accept_confirmation,
            command=replace(lab[2], confirmation_id=f"cnf_{index}"),
            clock=lambda: ON_TIME,
        )
    assert invoke(lab, service.recover_pending_confirmations, limit=2) == (
        "cnf_0",
        "cnf_1",
    )
    assert invoke(lab, service.recover_pending_confirmations, limit=2) == ("cnf_2",)
    assert_result(
        lab,
        "CAPTURED",
        receipts=3,
        dispositions=["applied", "already_resolved", "already_resolved"],
    )


def test_recovery_failure_keeps_current_receipt_pending(lab, monkeypatch):
    invoke(lab, service.accept_confirmation, command=lab[2], clock=lambda: ON_TIME)

    def fail(*args, **kwargs):
        raise RuntimeError("event failed")

    monkeypatch.setattr(service, "create_outbox_event", fail)
    with pytest.raises(RuntimeError, match="event failed"):
        invoke(lab, service.recover_pending_confirmations)
    with lab[1]() as session:
        assert not session.get(
            ConfirmationReceiptRecord, lab[2].confirmation_id
        ).completed


def test_receipt_commit_failure_does_not_protect_payment(lab, monkeypatch):
    with lab[1]() as session:

        def fail():
            raise OperationalError("COMMIT", {}, RuntimeError("disk unavailable"))

        monkeypatch.setattr(session, "commit", fail)
        with pytest.raises(service.ConfirmationProcessingUnavailableError):
            service.process_confirmation(session, command=lab[2], clock=lambda: ON_TIME)
    invoke(lab, service.expire_due_payments, now=DEADLINE)
    assert_result(lab, "EXPIRED", receipts=0, dispositions=[])


@pytest.mark.parametrize("limit", [0, 1001, True, 1.5])
def test_recovery_rejects_invalid_limit(lab, limit):
    with pytest.raises(ValueError, match="limit must"):
        invoke(lab, service.recover_pending_confirmations, limit=limit)


def test_missing_receipt_cannot_be_completed(lab):
    with pytest.raises(service.ConfirmationNotFoundError):
        invoke(lab, service.complete_confirmation, "cnf_missing")


def test_dirty_caller_session_is_not_silently_committed(lab):
    with lab[1]() as session:
        payment = session.get(PaymentRecord, lab[3])
        payment.merchant_reference = "uncommitted-edit"
        with pytest.raises(ValueError, match="clean session"):
            service.accept_confirmation(session, command=lab[2], clock=lambda: ON_TIME)
        assert payment in session.dirty
