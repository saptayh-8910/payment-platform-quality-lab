"""Frozen reporting evidence, cutoff boundaries and concurrent first generation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event, current_thread

import pytest
from sqlalchemy import event, select, text

from payment_quality_lab.domain.payment import Currency, DelayedPaymentDecision
from payment_quality_lab.persistence.migrations import upgrade_database
from payment_quality_lab.persistence.models import ConfirmationReportRecord
from payment_quality_lab.services import confirmation_reporting as reporting
from payment_quality_lab.services.confirmations import (
    ConfirmationCommand,
    ConfirmationIdConflictError,
    accept_confirmation,
    complete_confirmation,
    expire_due_payments,
    process_confirmation,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
    cancel_payment,
)
from payment_quality_lab.services.reconciliation import create_settlement_batch

START = datetime(2026, 9, 1, tzinfo=UTC)
CUTOFF = START + timedelta(hours=1)


@pytest.fixture
def lab(app):
    return app.state.session_factory


def create(lab, key="report-payment", currency=Currency.JPY):
    with lab() as session:
        return authorize_payment(
            session,
            command=AuthorizationCommand(
                key, 2500, currency, DelayedPaymentDecision.AWAIT_CONFIRMATION
            ),
            idempotency_key=key,
            clock=lambda: START,
        ).payment


def batch(lab, cutoff=CUTOFF):
    with lab() as session:
        return create_settlement_batch(session, cutoff=cutoff, entries=[]).id


def report(lab, batch_id):
    with lab() as session:
        return reporting.confirmation_section(session, batch_id)


def command(payment, identity="cnf_report"):
    return ConfirmationCommand(
        identity, payment.payment_reference, 2500, Currency(payment.currency)
    )


@pytest.mark.parametrize("seconds,expected", [(-1, 1), (0, 1), (1, 0)])
def test_cutoff_inclusive_and_later_state_not_used(lab, seconds, expected):
    payment = create(lab)
    with lab() as session:
        process_confirmation(
            session,
            command=command(payment),
            received_at=CUTOFF + timedelta(seconds=seconds),
        )
    result = report(lab, batch(lab))
    assert result["payment_outcomes"]["confirmed_on_time"] == expected
    assert result["payment_outcomes"]["pending"] == 1 - expected
    assert result["dispositions"]["applied"] == expected


def test_pending_recovery_cannot_rewrite_saved_report(lab):
    payment = create(lab)
    with lab() as session:
        accept_confirmation(session, command=command(payment), clock=lambda: CUTOFF)
    first_batch = batch(lab)
    before = report(lab, first_batch)
    assert before["pending_receipt_count"] == 1
    with lab() as session:
        complete_confirmation(session, "cnf_report")
    assert report(lab, first_batch) == before
    after = report(lab, batch(lab))
    assert after["pending_receipt_count"] == 0
    assert after["payment_outcomes"]["confirmed_on_time"] == 1
    assert after["generated_at"] >= before["generated_at"]


def test_anomalies_separate_currency_and_replays(lab):
    payment = create(lab)
    commands = [
        replace(command(payment), amount=100),
        replace(command(payment, "cnf_usd"), currency=Currency.USD),
        replace(command(payment, "cnf_unknown"), payment_reference="ref_unknown"),
    ]
    for item in commands:
        with lab() as session:
            process_confirmation(session, command=item, received_at=CUTOFF)
            process_confirmation(session, command=item, received_at=CUTOFF)
            with pytest.raises(ConfirmationIdConflictError):
                process_confirmation(
                    session,
                    command=replace(item, amount=item.amount + 1),
                    received_at=CUTOFF,
                )
    result = report(lab, batch(lab))
    assert sum(result["dispositions"].values()) == 3
    assert result["observed_anomalies"] == [
        {
            "currency": "JPY",
            "disposition": "amount_mismatch",
            "count": 1,
            "observed_amount": 100,
        },
        {
            "currency": "JPY",
            "disposition": "unknown_reference",
            "count": 1,
            "observed_amount": 2500,
        },
        {
            "currency": "USD",
            "disposition": "currency_mismatch",
            "count": 1,
            "observed_amount": 2500,
        },
    ]
    assert payment.id not in str(result)
    assert "cnf_report" not in str(result)


def test_terminal_outcomes_and_cutoff(lab):
    cancelled = create(lab, "cancel-report")
    create(lab, "expire-report")
    with lab() as session:
        cancel_payment(
            session, payment_id=cancelled.id, idempotency_key="cancel-report-key"
        )
        expire_due_payments(session, now=START + timedelta(hours=72))
    historical = report(lab, batch(lab))
    assert historical["payment_outcomes"]["pending"] == 2
    current = report(lab, batch(lab, datetime.now(UTC)))
    assert current["payment_outcomes"]["cancelled_unconfirmed"] == 1
    assert current["payment_outcomes"]["expired_without_on_time_confirmation"] == 1


def test_mixed_outcomes_late_and_resolved_evidence(lab):
    paid = create(lab, "paid-report")
    overdue = create(lab, "overdue-report")
    create(lab, "pending-report")
    with lab() as session:
        process_confirmation(session, command=command(paid), received_at=CUTOFF)
        process_confirmation(
            session, command=command(paid, "cnf_second"), received_at=CUTOFF
        )
        process_confirmation(
            session,
            command=command(overdue, "cnf_late"),
            received_at=START + timedelta(hours=73),
        )
    result = report(lab, batch(lab, START + timedelta(hours=74)))
    assert result["payment_count"] == 3
    assert result["payment_outcomes"] == {
        "confirmed_on_time": 1,
        "expired_without_on_time_confirmation": 1,
        "pending": 1,
        "cancelled_unconfirmed": 0,
    }
    assert (
        result["dispositions"]["applied"]
        == result["dispositions"]["late"]
        == result["dispositions"]["already_resolved"]
        == 1
    )


def test_missing_batch_and_invalid_clock_leave_no_snapshot(lab):
    with lab() as session, pytest.raises(LookupError):
        reporting.confirmation_section(session, "missing")
    identity = batch(lab)
    with lab() as session:
        with pytest.raises(ValueError):
            reporting.confirmation_section(
                session, identity, clock=lambda: datetime(2026, 1, 1)
            )
        assert session.get(ConfirmationReportRecord, identity) is None


def test_failed_write_does_not_save_partial_report(lab, monkeypatch):
    identity = batch(lab)
    with lab() as session:

        def fail():
            raise RuntimeError("simulated report commit failure")

        monkeypatch.setattr(session, "commit", fail)
        with pytest.raises(RuntimeError):
            reporting.confirmation_section(session, identity)
    with lab() as session:
        assert session.get(ConfirmationReportRecord, identity) is None
    assert report(lab, identity)["payment_count"] == 0


def test_concurrent_first_generation_saves_one_result(lab, app):
    identity = batch(lab)
    paused, release, contender = Event(), Event(), Event()
    connections = set()

    def observe(connection, cursor, statement, parameters, context, many):
        if statement == "BEGIN IMMEDIATE":
            connections.add(id(connection.connection.driver_connection))
            if current_thread().name.startswith("reader"):
                contender.set()

    def clock():
        paused.set()
        assert release.wait(5)
        return CUTOFF

    def owner():
        with lab() as session:
            return reporting.confirmation_section(session, identity, clock=clock)

    event.listen(app.state.engine, "before_cursor_execute", observe)
    try:
        with (
            ThreadPoolExecutor(1) as a,
            ThreadPoolExecutor(1, thread_name_prefix="reader") as b,
        ):
            first = a.submit(owner)
            try:
                assert paused.wait(5)
                second = b.submit(report, lab, identity)
                assert contender.wait(5)
                assert not second.done()
            finally:
                release.set()
            assert first.result() == second.result()
        assert len(connections) == 2
    finally:
        event.remove(app.state.engine, "before_cursor_execute", observe)
    with lab() as session:
        assert len(list(session.scalars(select(ConfirmationReportRecord)))) == 1


def test_migration_adds_empty_reports_without_backdating(app, lab):
    payment = create(lab)
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE confirmation_reports"))
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('0005_receipts')"))
    assert upgrade_database(str(app.state.engine.url)) == "0006_reports"
    assert upgrade_database(str(app.state.engine.url)) == "0006_reports"
    with lab() as session:
        assert list(session.scalars(select(ConfirmationReportRecord))) == []
    assert report(lab, batch(lab))["payment_count"] == 1
    assert payment.amount == 2500
