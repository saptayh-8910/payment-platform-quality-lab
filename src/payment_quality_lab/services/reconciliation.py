"""Synthetic settlement import and read-only financial reconciliation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    ProcessedWebhookRecord,
    SettlementBatchRecord,
    SettlementRecord,
    WebhookEventRecord,
)


class SettlementBatchNotFoundError(LookupError):
    """Requested synthetic settlement batch does not exist."""


class SettlementPaymentNotFoundError(LookupError):
    """A settlement row refers to a payment outside the simulator."""


class SettlementPaymentOutsideCutoffError(ValueError):
    """A settlement row refers to a payment created after its batch cutoff."""


class SettlementCurrency(StrEnum):
    """Currency values accepted from the independent settlement source."""

    USD = "USD"
    JPY = "JPY"


class SettlementClassification(StrEnum):
    """Result of comparing one payment with its settlement rows."""

    MATCHED = "matched"
    MISSING = "missing"
    DUPLICATED = "duplicated"
    AMOUNT_MISMATCHED = "amount_mismatched"


class SourceCheckStatus(StrEnum):
    """Agreement state for an independent ledger or webhook source."""

    MATCHED = "matched"
    MISSING = "missing"
    STALE = "stale"
    MISMATCHED = "mismatched"


class ReconciliationStatus(StrEnum):
    """Overall report outcome."""

    MATCHED = "matched"
    MISMATCHED = "mismatched"


@dataclass(frozen=True, slots=True)
class SettlementInput:
    """One row received from the synthetic external settlement source."""

    payment_id: str
    amount: int
    currency: SettlementCurrency


@dataclass(frozen=True, slots=True)
class LedgerTotals:
    """Financial totals calculated only from immutable ledger entries."""

    authorized: int = 0
    captured: int = 0
    refunded: int = 0

    @property
    def net_captured(self) -> int:
        return self.captured - self.refunded


@dataclass(frozen=True, slots=True)
class SettlementComparison:
    """Pure result for one expected amount and its observed rows."""

    classification: SettlementClassification
    observed_amounts: tuple[int, ...]
    observed_currencies: tuple[str, ...]
    canonical_observed_amount: int


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    """Evidence for one payment across all independent sources."""

    payment_id: str
    merchant_reference: str
    currency: str
    expected_settlement_amount: int
    settlement_classification: SettlementClassification
    settlement_record_count: int
    observed_settlement_amounts: tuple[int, ...]
    observed_settlement_currencies: tuple[str, ...]
    ledger_status: SourceCheckStatus
    payment_authorized_amount: int
    ledger_authorized_amount: int
    payment_captured_amount: int
    ledger_captured_amount: int
    payment_refunded_amount: int
    ledger_refunded_amount: int
    projection_status: SourceCheckStatus
    expected_projection_version: int
    observed_projection_version: int | None
    latest_event_processed: bool


@dataclass(frozen=True, slots=True)
class CurrencyReconciliationTotal:
    """Financial totals that never combine different currencies."""

    currency: str
    expected_settlement_total: int
    observed_settlement_total: int
    net_discrepancy: int


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """Deterministic report totals and mismatch counts."""

    status: ReconciliationStatus
    payment_count: int
    currency_totals: tuple[CurrencyReconciliationTotal, ...]
    matched_count: int
    missing_count: int
    duplicated_count: int
    amount_mismatched_count: int
    ledger_mismatch_count: int
    projection_mismatch_count: int


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Repeatable read-only result for one immutable settlement batch."""

    batch_id: str
    cutoff: datetime
    items: tuple[ReconciliationItem, ...]
    summary: ReconciliationSummary


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def calculate_ledger_totals(
    entries: list[LedgerEntryRecord],
    *,
    cutoff: datetime | None = None,
) -> LedgerTotals:
    """Calculate supported financial totals, optionally through a cutoff."""
    resolved_cutoff = _as_utc(cutoff) if cutoff is not None else None
    authorized = 0
    captured = 0
    refunded = 0
    for entry in entries:
        if resolved_cutoff is not None and _as_utc(entry.created_at) > resolved_cutoff:
            continue
        if entry.operation == "AUTHORIZATION":
            authorized += entry.amount
        elif entry.operation == "CAPTURE":
            captured += entry.amount
        elif entry.operation == "CONFIRMATION_CAPTURE":
            authorized += entry.amount
            captured += entry.amount
        elif entry.operation == "REFUND":
            refunded += entry.amount
    return LedgerTotals(
        authorized=authorized,
        captured=captured,
        refunded=refunded,
    )


def classify_settlement(
    *,
    expected_amount: int,
    expected_currency: str,
    records: list[SettlementRecord],
) -> SettlementComparison:
    """Classify rows without counting duplicate values more than once."""
    ordered = sorted(records, key=lambda record: record.line_number)
    amounts = tuple(record.amount for record in ordered)
    currencies = tuple(record.currency for record in ordered)
    canonical = amounts[0] if amounts else 0

    if len(ordered) > 1:
        classification = SettlementClassification.DUPLICATED
    elif not ordered:
        classification = (
            SettlementClassification.MATCHED
            if expected_amount == 0
            else SettlementClassification.MISSING
        )
    elif canonical == expected_amount and currencies[0] == expected_currency:
        classification = SettlementClassification.MATCHED
    else:
        classification = SettlementClassification.AMOUNT_MISMATCHED

    return SettlementComparison(
        classification=classification,
        observed_amounts=amounts,
        observed_currencies=currencies,
        canonical_observed_amount=canonical,
    )


def create_settlement_batch(
    session: Session,
    *,
    cutoff: datetime,
    entries: list[SettlementInput],
) -> SettlementBatchRecord:
    """Atomically import one synthetic external settlement batch."""
    resolved_cutoff = _as_utc(cutoff)
    payment_ids = {entry.payment_id for entry in entries}
    if payment_ids:
        known_payments = {
            payment.id: payment
            for payment in session.scalars(
                select(PaymentRecord).where(PaymentRecord.id.in_(payment_ids))
            )
        }
        missing = sorted(payment_ids - known_payments.keys())
        if missing:
            raise SettlementPaymentNotFoundError(missing[0])
        outside_cutoff = sorted(
            payment_id
            for payment_id, payment in known_payments.items()
            if _as_utc(payment.created_at) > resolved_cutoff
        )
        if outside_cutoff:
            raise SettlementPaymentOutsideCutoffError(outside_cutoff[0])

    now = datetime.now(UTC)
    batch = SettlementBatchRecord(
        id=f"setb_{uuid4().hex}",
        cutoff=resolved_cutoff,
        created_at=now,
    )
    try:
        session.add(batch)
        session.flush()
        for line_number, entry in enumerate(entries, start=1):
            session.add(
                SettlementRecord(
                    id=f"set_{uuid4().hex}",
                    batch_id=batch.id,
                    payment_id=entry.payment_id,
                    line_number=line_number,
                    amount=entry.amount,
                    currency=entry.currency.value,
                    created_at=now,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return batch


def get_settlement_records(
    session: Session,
    batch_id: str,
) -> list[SettlementRecord]:
    """Return settlement rows in stable source order."""
    if session.get(SettlementBatchRecord, batch_id) is None:
        raise SettlementBatchNotFoundError(batch_id)
    statement = (
        select(SettlementRecord)
        .where(SettlementRecord.batch_id == batch_id)
        .order_by(SettlementRecord.line_number)
    )
    return list(session.scalars(statement))


def _ledger_status(payment: PaymentRecord, totals: LedgerTotals) -> SourceCheckStatus:
    if (
        payment.authorized_amount == totals.authorized
        and payment.captured_amount == totals.captured
        and payment.refunded_amount == totals.refunded
    ):
        return SourceCheckStatus.MATCHED
    return SourceCheckStatus.MISMATCHED


def _projection_status(
    payment: PaymentRecord,
    projection: MerchantPaymentProjectionRecord | None,
    latest_event: WebhookEventRecord,
    latest_event_processed: bool,
) -> SourceCheckStatus:
    if projection is None:
        return SourceCheckStatus.MISSING
    if projection.aggregate_version < latest_event.aggregate_version:
        return SourceCheckStatus.STALE
    if not latest_event_processed:
        return SourceCheckStatus.MISSING
    if (
        projection.aggregate_version != payment.version
        or projection.merchant_reference != payment.merchant_reference
        or projection.amount != payment.amount
        or projection.currency != payment.currency
        or projection.status != payment.status
        or projection.decline_reason != payment.decline_reason
        or projection.authorized_amount != payment.authorized_amount
        or projection.captured_amount != payment.captured_amount
        or projection.refunded_amount != payment.refunded_amount
    ):
        return SourceCheckStatus.MISMATCHED
    return SourceCheckStatus.MATCHED


def reconcile_settlement_batch(
    session: Session,
    *,
    batch_id: str,
) -> ReconciliationReport:
    """Compare independent sources without changing any persisted state."""
    batch = session.get(SettlementBatchRecord, batch_id)
    if batch is None:
        raise SettlementBatchNotFoundError(batch_id)
    cutoff = _as_utc(batch.cutoff)

    payments = list(
        session.scalars(
            select(PaymentRecord)
            .where(PaymentRecord.created_at <= cutoff)
            .order_by(PaymentRecord.id)
        )
    )
    all_settlements = get_settlement_records(session, batch_id)
    settlements_by_payment: dict[str, list[SettlementRecord]] = {}
    for record in all_settlements:
        settlements_by_payment.setdefault(record.payment_id, []).append(record)

    items: list[ReconciliationItem] = []
    totals_by_currency: dict[str, list[int]] = {}
    for payment in payments:
        entries = list(
            session.scalars(
                select(LedgerEntryRecord)
                .where(LedgerEntryRecord.payment_id == payment.id)
                .order_by(LedgerEntryRecord.created_at, LedgerEntryRecord.id)
            )
        )
        current_ledger = calculate_ledger_totals(entries)
        cutoff_ledger = calculate_ledger_totals(entries, cutoff=cutoff)
        expected_amount = max(0, cutoff_ledger.net_captured)
        settlement = classify_settlement(
            expected_amount=expected_amount,
            expected_currency=payment.currency,
            records=settlements_by_payment.get(payment.id, []),
        )

        latest_event = session.scalar(
            select(WebhookEventRecord)
            .where(WebhookEventRecord.payment_id == payment.id)
            .order_by(WebhookEventRecord.aggregate_version.desc())
            .limit(1)
        )
        if latest_event is None:  # pragma: no cover - outbox is transactional
            raise RuntimeError(f"Payment {payment.id} has no webhook event")
        latest_processed = (
            session.get(ProcessedWebhookRecord, latest_event.id) is not None
        )
        projection = session.get(MerchantPaymentProjectionRecord, payment.id)
        projection_status = _projection_status(
            payment,
            projection,
            latest_event,
            latest_processed,
        )

        expected_totals = totals_by_currency.setdefault(payment.currency, [0, 0])
        expected_totals[0] += expected_amount
        if settlement.observed_currencies:
            observed_currency = settlement.observed_currencies[0]
            observed_totals = totals_by_currency.setdefault(observed_currency, [0, 0])
            observed_totals[1] += settlement.canonical_observed_amount
        items.append(
            ReconciliationItem(
                payment_id=payment.id,
                merchant_reference=payment.merchant_reference,
                currency=payment.currency,
                expected_settlement_amount=expected_amount,
                settlement_classification=settlement.classification,
                settlement_record_count=len(settlement.observed_amounts),
                observed_settlement_amounts=settlement.observed_amounts,
                observed_settlement_currencies=settlement.observed_currencies,
                ledger_status=_ledger_status(payment, current_ledger),
                payment_authorized_amount=payment.authorized_amount,
                ledger_authorized_amount=current_ledger.authorized,
                payment_captured_amount=payment.captured_amount,
                ledger_captured_amount=current_ledger.captured,
                payment_refunded_amount=payment.refunded_amount,
                ledger_refunded_amount=current_ledger.refunded,
                projection_status=projection_status,
                expected_projection_version=latest_event.aggregate_version,
                observed_projection_version=(
                    projection.aggregate_version if projection is not None else None
                ),
                latest_event_processed=latest_processed,
            )
        )

    classifications = [item.settlement_classification for item in items]
    ledger_mismatch_count = sum(
        item.ledger_status is not SourceCheckStatus.MATCHED for item in items
    )
    projection_mismatch_count = sum(
        item.projection_status is not SourceCheckStatus.MATCHED for item in items
    )
    all_matched = (
        all(value is SettlementClassification.MATCHED for value in classifications)
        and ledger_mismatch_count == 0
        and projection_mismatch_count == 0
    )
    summary = ReconciliationSummary(
        status=(
            ReconciliationStatus.MATCHED
            if all_matched
            else ReconciliationStatus.MISMATCHED
        ),
        payment_count=len(items),
        currency_totals=tuple(
            CurrencyReconciliationTotal(
                currency=currency,
                expected_settlement_total=totals[0],
                observed_settlement_total=totals[1],
                net_discrepancy=totals[1] - totals[0],
            )
            for currency, totals in sorted(totals_by_currency.items())
        ),
        matched_count=classifications.count(SettlementClassification.MATCHED),
        missing_count=classifications.count(SettlementClassification.MISSING),
        duplicated_count=classifications.count(SettlementClassification.DUPLICATED),
        amount_mismatched_count=classifications.count(
            SettlementClassification.AMOUNT_MISMATCHED
        ),
        ledger_mismatch_count=ledger_mismatch_count,
        projection_mismatch_count=projection_mismatch_count,
    )
    return ReconciliationReport(
        batch_id=batch.id,
        cutoff=cutoff,
        items=tuple(items),
        summary=summary,
    )
