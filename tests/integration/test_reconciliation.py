"""Database evidence for settlement and multi-source reconciliation."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import AuthorizationDecision, Currency
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    ProcessedWebhookRecord,
    SettlementBatchRecord,
    SettlementRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
    cancel_payment,
    capture_payment,
    refund_payment,
)
from payment_quality_lab.services.reconciliation import (
    SettlementClassification,
    SettlementCurrency,
    SettlementInput,
    SourceCheckStatus,
    create_settlement_batch,
    reconcile_settlement_batch,
)
from payment_quality_lab.services.webhooks import (
    consume_webhook,
    dispatch_webhook,
)

SECRET = "whsec_reconciliation_synthetic"


@pytest.fixture
def factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'reconciliation.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def authorize_once(
    factory: sessionmaker[Session],
    *,
    reference: str,
    amount: int,
    currency: Currency = Currency.JPY,
    decision: AuthorizationDecision = AuthorizationDecision.APPROVE,
) -> str:
    with factory() as session:
        return authorize_payment(
            session,
            command=AuthorizationCommand(
                merchant_reference=reference,
                amount=amount,
                currency=currency,
                payment_method_token=decision,
            ),
            idempotency_key=f"reconcile-authorize-{reference}",
        ).payment.id


def capture_once(factory: sessionmaker[Session], payment_id: str, suffix: str) -> None:
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key=f"reconcile-capture-{suffix}",
        )


def deliver_events(factory: sessionmaker[Session], payment_id: str) -> None:
    def receiver(payload: bytes, signature: str, now: datetime) -> int:
        with factory() as consumer_session:
            consume_webhook(
                consumer_session,
                payload=payload,
                signature_header=signature,
                secret=SECRET,
                now=now,
            )
        return 200

    with factory() as session:
        events = list(
            session.scalars(
                select(WebhookEventRecord)
                .where(WebhookEventRecord.payment_id == payment_id)
                .order_by(WebhookEventRecord.aggregate_version)
            )
        )
        latest_time = max(event.created_at for event in events)
        if latest_time.tzinfo is None:
            latest_time = latest_time.replace(tzinfo=UTC)
        now = latest_time + timedelta(seconds=1)
        for event in events:
            dispatch_webhook(
                session,
                event_id=event.id,
                secret=SECRET,
                receiver=receiver,
                now=now,
            )


def batch_for(
    factory: sessionmaker[Session],
    entries: list[SettlementInput],
    *,
    cutoff: datetime | None = None,
) -> str:
    with factory() as session:
        batch = create_settlement_batch(
            session,
            cutoff=cutoff or datetime.now(UTC) + timedelta(seconds=5),
            entries=entries,
        )
        return batch.id


def reconcile(factory: sessionmaker[Session], batch_id: str):
    with factory() as session:
        return reconcile_settlement_batch(session, batch_id=batch_id)


def settlement(payment_id: str, amount: int, currency: str = "JPY") -> SettlementInput:
    return SettlementInput(
        payment_id=payment_id,
        amount=amount,
        currency=SettlementCurrency(currency),
    )


def test_matching_capture_balances_all_independent_sources(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="matched", amount=1000)
    capture_once(factory, payment_id, "matched")
    deliver_events(factory, payment_id)
    batch_id = batch_for(factory, [settlement(payment_id, 1000)])

    report = reconcile(factory, batch_id)

    assert report.summary.status.value == "matched"
    assert report.summary.matched_count == 1
    assert report.summary.currency_totals[0].net_discrepancy == 0
    item = report.items[0]
    assert item.settlement_classification is SettlementClassification.MATCHED
    assert item.ledger_status is SourceCheckStatus.MATCHED
    assert item.projection_status is SourceCheckStatus.MATCHED


def test_partial_refund_settles_capture_minus_cumulative_refunds(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="partial-refund", amount=1000)
    capture_once(factory, payment_id, "partial-refund")
    with factory() as session:
        refund_payment(
            session,
            payment_id=payment_id,
            amount=250,
            idempotency_key="reconcile-refund-250",
        )
    deliver_events(factory, payment_id)
    batch_id = batch_for(factory, [settlement(payment_id, 750)])

    report = reconcile(factory, batch_id)

    assert report.items[0].expected_settlement_amount == 750
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED


def test_fully_refunded_payment_requires_no_settlement_row(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="full-refund", amount=1000)
    capture_once(factory, payment_id, "full-refund")
    with factory() as session:
        refund_payment(
            session,
            payment_id=payment_id,
            amount=1000,
            idempotency_key="reconcile-refund-full",
        )
    deliver_events(factory, payment_id)
    batch_id = batch_for(factory, [])

    report = reconcile(factory, batch_id)

    assert report.items[0].expected_settlement_amount == 0
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED


@pytest.mark.parametrize("terminal_state", ["declined", "cancelled"])
def test_declined_or_cancelled_payment_requires_no_settlement_row(
    factory: sessionmaker[Session],
    terminal_state: str,
) -> None:
    payment_id = authorize_once(
        factory,
        reference=terminal_state,
        amount=1000,
        decision=(
            AuthorizationDecision.DECLINE
            if terminal_state == "declined"
            else AuthorizationDecision.APPROVE
        ),
    )
    if terminal_state == "cancelled":
        with factory() as session:
            cancel_payment(
                session,
                payment_id=payment_id,
                idempotency_key="reconcile-cancel",
            )
    deliver_events(factory, payment_id)
    batch_id = batch_for(factory, [])

    report = reconcile(factory, batch_id)

    assert report.items[0].expected_settlement_amount == 0
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED


def test_jpy_and_usd_totals_are_reported_separately(
    factory: sessionmaker[Session],
) -> None:
    jpy_id = authorize_once(factory, reference="jpy", amount=1234)
    usd_id = authorize_once(
        factory,
        reference="usd",
        amount=1099,
        currency=Currency.USD,
    )
    capture_once(factory, jpy_id, "jpy")
    capture_once(factory, usd_id, "usd")
    deliver_events(factory, jpy_id)
    deliver_events(factory, usd_id)
    batch_id = batch_for(
        factory,
        [settlement(jpy_id, 1234), settlement(usd_id, 1099, "USD")],
    )

    report = reconcile(factory, batch_id)

    assert [total.currency for total in report.summary.currency_totals] == [
        "JPY",
        "USD",
    ]
    assert [
        (total.expected_settlement_total, total.observed_settlement_total)
        for total in report.summary.currency_totals
    ] == [(1234, 1234), (1099, 1099)]


def test_missing_settlement_is_identified(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="missing", amount=1000)
    capture_once(factory, payment_id, "missing")
    deliver_events(factory, payment_id)

    report = reconcile(factory, batch_for(factory, []))

    assert report.items[0].settlement_classification is SettlementClassification.MISSING
    assert report.summary.missing_count == 1
    assert report.summary.currency_totals[0].net_discrepancy == -1000


def test_duplicate_rows_are_flagged_without_double_counting_total(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="duplicate", amount=1000)
    capture_once(factory, payment_id, "duplicate")
    deliver_events(factory, payment_id)
    batch_id = batch_for(
        factory,
        [settlement(payment_id, 1000), settlement(payment_id, 1000)],
    )

    report = reconcile(factory, batch_id)

    assert (
        report.items[0].settlement_classification is SettlementClassification.DUPLICATED
    )
    assert report.items[0].settlement_record_count == 2
    total = report.summary.currency_totals[0]
    assert total.observed_settlement_total == 1000
    assert total.net_discrepancy == 0


@pytest.mark.parametrize(
    ("amount", "currency"),
    [(900, "JPY"), (1000, "USD")],
)
def test_amount_or_currency_difference_is_identified(
    factory: sessionmaker[Session],
    amount: int,
    currency: str,
) -> None:
    payment_id = authorize_once(factory, reference=f"mismatch-{currency}", amount=1000)
    capture_once(factory, payment_id, f"mismatch-{currency}")
    deliver_events(factory, payment_id)

    report = reconcile(
        factory,
        batch_for(factory, [settlement(payment_id, amount, currency)]),
    )

    assert (
        report.items[0].settlement_classification
        is SettlementClassification.AMOUNT_MISMATCHED
    )
    if currency == "USD":
        assert [
            (
                total.currency,
                total.expected_settlement_total,
                total.observed_settlement_total,
            )
            for total in report.summary.currency_totals
        ] == [("JPY", 1000, 0), ("USD", 0, 1000)]


@pytest.mark.parametrize("projection_case", ["missing", "stale"])
def test_projection_problem_is_reported_independently(
    factory: sessionmaker[Session],
    projection_case: str,
) -> None:
    payment_id = authorize_once(
        factory, reference=f"projection-{projection_case}", amount=1000
    )
    if projection_case == "stale":
        deliver_events(factory, payment_id)
    capture_once(factory, payment_id, f"projection-{projection_case}")
    batch_id = batch_for(factory, [settlement(payment_id, 1000)])

    report = reconcile(factory, batch_id)

    expected = (
        SourceCheckStatus.MISSING
        if projection_case == "missing"
        else SourceCheckStatus.STALE
    )
    assert report.items[0].projection_status is expected
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED
    assert report.summary.projection_mismatch_count == 1


@pytest.mark.parametrize("consumer_problem", ["inbox_missing", "content_mismatched"])
def test_consumer_source_disagreement_is_not_hidden_by_matching_settlement(
    factory: sessionmaker[Session],
    consumer_problem: str,
) -> None:
    payment_id = authorize_once(
        factory,
        reference=f"consumer-{consumer_problem}",
        amount=1000,
    )
    capture_once(factory, payment_id, f"consumer-{consumer_problem}")
    deliver_events(factory, payment_id)
    with factory() as session:
        latest_event = session.scalar(
            select(WebhookEventRecord)
            .where(WebhookEventRecord.payment_id == payment_id)
            .order_by(WebhookEventRecord.aggregate_version.desc())
            .limit(1)
        )
        assert latest_event is not None
        if consumer_problem == "inbox_missing":
            inbox = session.get(ProcessedWebhookRecord, latest_event.id)
            assert inbox is not None
            session.delete(inbox)
        else:
            projection = session.get(MerchantPaymentProjectionRecord, payment_id)
            assert projection is not None
            projection.captured_amount = 999
        session.commit()
    batch_id = batch_for(factory, [settlement(payment_id, 1000)])

    report = reconcile(factory, batch_id)

    expected = (
        SourceCheckStatus.MISSING
        if consumer_problem == "inbox_missing"
        else SourceCheckStatus.MISMATCHED
    )
    assert report.items[0].projection_status is expected
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED


def test_payment_and_ledger_difference_shows_exact_totals(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="ledger-mismatch", amount=1000)
    capture_once(factory, payment_id, "ledger-mismatch")
    deliver_events(factory, payment_id)
    with factory() as session:
        session.add(
            LedgerEntryRecord(
                id="led_injected_extra_refund",
                payment_id=payment_id,
                operation="REFUND",
                amount=100,
                currency="JPY",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    batch_id = batch_for(factory, [settlement(payment_id, 900)])

    report = reconcile(factory, batch_id)
    item = report.items[0]

    assert item.ledger_status is SourceCheckStatus.MISMATCHED
    assert (item.payment_refunded_amount, item.ledger_refunded_amount) == (0, 100)
    assert item.settlement_classification is SettlementClassification.MATCHED


def test_one_batch_summarizes_all_settlement_classifications(
    factory: sessionmaker[Session],
) -> None:
    amounts = {
        "batch-matched": 100,
        "batch-missing": 200,
        "batch-duplicated": 300,
        "batch-mismatched": 400,
    }
    payment_ids: dict[str, str] = {}
    for reference, amount in amounts.items():
        payment_id = authorize_once(factory, reference=reference, amount=amount)
        capture_once(factory, payment_id, reference)
        deliver_events(factory, payment_id)
        payment_ids[reference] = payment_id
    batch_id = batch_for(
        factory,
        [
            settlement(payment_ids["batch-matched"], 100),
            settlement(payment_ids["batch-duplicated"], 300),
            settlement(payment_ids["batch-duplicated"], 300),
            settlement(payment_ids["batch-mismatched"], 450),
        ],
    )

    report = reconcile(factory, batch_id)

    assert (
        report.summary.matched_count,
        report.summary.missing_count,
        report.summary.duplicated_count,
        report.summary.amount_mismatched_count,
    ) == (1, 1, 1, 1)
    total = report.summary.currency_totals[0]
    assert (total.expected_settlement_total, total.observed_settlement_total) == (
        1000,
        850,
    )


def test_cutoff_includes_capture_at_boundary_and_excludes_later_refund(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="cutoff", amount=1000)
    capture_once(factory, payment_id, "cutoff")
    with factory() as session:
        refund_payment(
            session,
            payment_id=payment_id,
            amount=250,
            idempotency_key="reconcile-cutoff-refund",
        )
    deliver_events(factory, payment_id)
    cutoff = datetime.now(UTC) + timedelta(seconds=10)
    with factory() as session:
        entries = list(
            session.scalars(
                select(LedgerEntryRecord).where(
                    LedgerEntryRecord.payment_id == payment_id
                )
            )
        )
        for entry in entries:
            if entry.operation == "AUTHORIZATION":
                entry.created_at = cutoff - timedelta(seconds=1)
            elif entry.operation == "CAPTURE":
                entry.created_at = cutoff
            elif entry.operation == "REFUND":
                entry.created_at = cutoff + timedelta(seconds=1)
        session.commit()
    batch_id = batch_for(
        factory,
        [settlement(payment_id, 1000)],
        cutoff=cutoff,
    )

    report = reconcile(factory, batch_id)

    assert report.items[0].expected_settlement_amount == 1000
    assert report.items[0].ledger_status is SourceCheckStatus.MATCHED
    assert report.items[0].settlement_classification is SettlementClassification.MATCHED


def test_repeated_reconciliation_is_identical_and_read_only(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="repeatable", amount=1000)
    capture_once(factory, payment_id, "repeatable")
    deliver_events(factory, payment_id)
    batch_id = batch_for(factory, [settlement(payment_id, 1000)])

    with factory() as session:
        before = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in (
                PaymentRecord,
                LedgerEntryRecord,
                SettlementBatchRecord,
                SettlementRecord,
            )
        }
        first = reconcile_settlement_batch(session, batch_id=batch_id)
        second = reconcile_settlement_batch(session, batch_id=batch_id)
        after = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in (
                PaymentRecord,
                LedgerEntryRecord,
                SettlementBatchRecord,
                SettlementRecord,
            )
        }

    assert first == second
    assert before == after


def test_invalid_settlement_row_rolls_back_complete_batch(
    factory: sessionmaker[Session],
) -> None:
    payment_id = authorize_once(factory, reference="invalid-batch", amount=1000)
    with factory() as session:
        with pytest.raises(IntegrityError):
            create_settlement_batch(
                session,
                cutoff=datetime.now(UTC),
                entries=[settlement(payment_id, -1)],
            )

        assert (
            session.scalar(select(func.count()).select_from(SettlementBatchRecord)) == 0
        )
        assert session.scalar(select(func.count()).select_from(SettlementRecord)) == 0
