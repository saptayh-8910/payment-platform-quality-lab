"""Public API request and response schemas."""

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    PaymentStatus,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    SettlementBatchRecord,
    SettlementRecord,
    WebhookDeliveryAttemptRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.payments import PaymentSnapshot
from payment_quality_lab.services.reconciliation import (
    CurrencyReconciliationTotal,
    ReconciliationItem,
    ReconciliationReport,
    ReconciliationSummary,
    SettlementCurrency,
)
from payment_quality_lab.services.webhooks import ConsumerOutcome, DeliveryResult


def _as_utc(value: datetime) -> datetime:
    """Restore UTC metadata that SQLite does not retain."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthorizePaymentRequest(BaseModel):
    """Authorization inputs accepted by the simulator."""

    model_config = ConfigDict(extra="forbid")

    merchant_reference: str = Field(min_length=1, max_length=64)
    amount: int = Field(gt=0, le=999_999_999)
    currency: Currency
    payment_method_token: AuthorizationDecision


class RefundPaymentRequest(BaseModel):
    """Amount to refund from captured funds."""

    model_config = ConfigDict(extra="forbid")

    amount: int = Field(gt=0, le=999_999_999)


class PaymentResponse(BaseModel):
    """Stable representation of the payment aggregate."""

    id: str
    merchant_reference: str
    amount: int
    currency: Currency
    status: PaymentStatus
    authorized_amount: int
    captured_amount: int
    refunded_amount: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, payment: PaymentRecord | PaymentSnapshot) -> "PaymentResponse":
        """Map persistence data without exposing ORM internals."""
        return cls(
            id=payment.id,
            merchant_reference=payment.merchant_reference,
            amount=payment.amount,
            currency=Currency(payment.currency),
            status=PaymentStatus(payment.status),
            authorized_amount=payment.authorized_amount,
            captured_amount=payment.captured_amount,
            refunded_amount=payment.refunded_amount,
            version=payment.version,
            created_at=_as_utc(payment.created_at),
            updated_at=_as_utc(payment.updated_at),
        )


class LedgerEntryResponse(BaseModel):
    """Public representation of an immutable ledger entry."""

    id: str
    payment_id: str
    operation: str
    amount: int
    currency: Currency
    created_at: datetime

    @classmethod
    def from_record(cls, entry: LedgerEntryRecord) -> "LedgerEntryResponse":
        """Map a ledger persistence record to the public schema."""
        return cls(
            id=entry.id,
            payment_id=entry.payment_id,
            operation=entry.operation,
            amount=entry.amount,
            currency=Currency(entry.currency),
            created_at=_as_utc(entry.created_at),
        )


class ErrorResponse(BaseModel):
    """Consistent service error body."""

    code: str
    message: str


class WebhookEventResponse(BaseModel):
    """Public producer view of one transactional outbox event."""

    id: str
    payment_id: str
    type: str
    aggregate_version: int
    payload: dict[str, Any]
    status: str
    attempt_count: int
    next_attempt_at: datetime
    created_at: datetime
    delivered_at: datetime | None

    @classmethod
    def from_record(cls, event: WebhookEventRecord) -> "WebhookEventResponse":
        return cls(
            id=event.id,
            payment_id=event.payment_id,
            type=event.event_type,
            aggregate_version=event.aggregate_version,
            payload=json.loads(event.payload),
            status=event.status,
            attempt_count=event.attempt_count,
            next_attempt_at=_as_utc(event.next_attempt_at),
            created_at=_as_utc(event.created_at),
            delivered_at=(
                _as_utc(event.delivered_at) if event.delivered_at is not None else None
            ),
        )


class WebhookDeliveryAttemptResponse(BaseModel):
    """Public delivery history for one webhook attempt."""

    attempt_number: int
    outcome: str
    response_status: int | None
    error_code: str | None
    attempted_at: datetime

    @classmethod
    def from_record(
        cls,
        attempt: WebhookDeliveryAttemptRecord,
    ) -> "WebhookDeliveryAttemptResponse":
        return cls(
            attempt_number=attempt.attempt_number,
            outcome=attempt.outcome,
            response_status=attempt.response_status,
            error_code=attempt.error_code,
            attempted_at=_as_utc(attempt.attempted_at),
        )


class WebhookConsumerResponse(BaseModel):
    """Result returned by the simulated merchant consumer."""

    event_id: str
    disposition: str
    duplicate: bool
    version_gap: bool

    @classmethod
    def from_outcome(cls, outcome: ConsumerOutcome) -> "WebhookConsumerResponse":
        return cls(
            event_id=outcome.event_id,
            disposition=outcome.disposition.value,
            duplicate=outcome.duplicate,
            version_gap=outcome.version_gap,
        )


class WebhookDeliveryResponse(BaseModel):
    """Result of one producer delivery attempt."""

    event_id: str
    attempt_number: int
    outcome: str
    status: str
    response_status: int | None
    next_attempt_at: datetime | None

    @classmethod
    def from_result(cls, result: DeliveryResult) -> "WebhookDeliveryResponse":
        return cls(
            event_id=result.event_id,
            attempt_number=result.attempt_number,
            outcome=result.outcome,
            status=result.status.value,
            response_status=result.response_status,
            next_attempt_at=result.next_attempt_at,
        )


class MerchantProjectionResponse(BaseModel):
    """Merchant payment view produced only from accepted webhooks."""

    payment_id: str
    merchant_reference: str
    amount: int
    currency: Currency
    status: PaymentStatus
    authorized_amount: int
    captured_amount: int
    refunded_amount: int
    aggregate_version: int
    last_event_id: str
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        projection: MerchantPaymentProjectionRecord,
    ) -> "MerchantProjectionResponse":
        return cls(
            payment_id=projection.payment_id,
            merchant_reference=projection.merchant_reference,
            amount=projection.amount,
            currency=Currency(projection.currency),
            status=PaymentStatus(projection.status),
            authorized_amount=projection.authorized_amount,
            captured_amount=projection.captured_amount,
            refunded_amount=projection.refunded_amount,
            aggregate_version=projection.aggregate_version,
            last_event_id=projection.last_event_id,
            updated_at=_as_utc(projection.updated_at),
        )


class SettlementEntryRequest(BaseModel):
    """One row in a synthetic external settlement batch."""

    model_config = ConfigDict(extra="forbid")

    payment_id: str = Field(min_length=1, max_length=40)
    amount: int = Field(gt=0, le=999_999_999)
    currency: SettlementCurrency


class SettlementBatchCreateRequest(BaseModel):
    """Immutable cutoff and rows imported from the settlement source."""

    model_config = ConfigDict(extra="forbid")

    cutoff: AwareDatetime
    entries: list[SettlementEntryRequest] = Field(max_length=1000)


class SettlementRecordResponse(BaseModel):
    """Public representation of one imported settlement row."""

    id: str
    payment_id: str
    line_number: int
    amount: int
    currency: SettlementCurrency
    created_at: datetime

    @classmethod
    def from_record(cls, record: SettlementRecord) -> "SettlementRecordResponse":
        return cls(
            id=record.id,
            payment_id=record.payment_id,
            line_number=record.line_number,
            amount=record.amount,
            currency=SettlementCurrency(record.currency),
            created_at=_as_utc(record.created_at),
        )


class SettlementBatchResponse(BaseModel):
    """Imported settlement batch and its source rows."""

    id: str
    cutoff: datetime
    created_at: datetime
    entries: list[SettlementRecordResponse]

    @classmethod
    def from_records(
        cls,
        batch: SettlementBatchRecord,
        records: list[SettlementRecord],
    ) -> "SettlementBatchResponse":
        return cls(
            id=batch.id,
            cutoff=_as_utc(batch.cutoff),
            created_at=_as_utc(batch.created_at),
            entries=[
                SettlementRecordResponse.from_record(record) for record in records
            ],
        )


class ReconciliationRequest(BaseModel):
    """Identify the immutable settlement batch to compare."""

    model_config = ConfigDict(extra="forbid")

    settlement_batch_id: str = Field(min_length=1, max_length=40)


class ReconciliationItemResponse(BaseModel):
    """Plain financial evidence for one payment."""

    payment_id: str
    merchant_reference: str
    currency: str
    expected_settlement_amount: int
    settlement_classification: str
    settlement_record_count: int
    observed_settlement_amounts: list[int]
    observed_settlement_currencies: list[str]
    ledger_status: str
    payment_authorized_amount: int
    ledger_authorized_amount: int
    payment_captured_amount: int
    ledger_captured_amount: int
    payment_refunded_amount: int
    ledger_refunded_amount: int
    projection_status: str
    expected_projection_version: int
    observed_projection_version: int | None
    latest_event_processed: bool

    @classmethod
    def from_result(cls, item: ReconciliationItem) -> "ReconciliationItemResponse":
        return cls(
            payment_id=item.payment_id,
            merchant_reference=item.merchant_reference,
            currency=item.currency,
            expected_settlement_amount=item.expected_settlement_amount,
            settlement_classification=item.settlement_classification.value,
            settlement_record_count=item.settlement_record_count,
            observed_settlement_amounts=list(item.observed_settlement_amounts),
            observed_settlement_currencies=list(item.observed_settlement_currencies),
            ledger_status=item.ledger_status.value,
            payment_authorized_amount=item.payment_authorized_amount,
            ledger_authorized_amount=item.ledger_authorized_amount,
            payment_captured_amount=item.payment_captured_amount,
            ledger_captured_amount=item.ledger_captured_amount,
            payment_refunded_amount=item.payment_refunded_amount,
            ledger_refunded_amount=item.ledger_refunded_amount,
            projection_status=item.projection_status.value,
            expected_projection_version=item.expected_projection_version,
            observed_projection_version=item.observed_projection_version,
            latest_event_processed=item.latest_event_processed,
        )


class ReconciliationSummaryResponse(BaseModel):
    """Totals and counts used for a release or investigation decision."""

    status: str
    payment_count: int
    currency_totals: list["CurrencyReconciliationTotalResponse"]
    matched_count: int
    missing_count: int
    duplicated_count: int
    amount_mismatched_count: int
    ledger_mismatch_count: int
    projection_mismatch_count: int

    @classmethod
    def from_result(
        cls,
        summary: ReconciliationSummary,
    ) -> "ReconciliationSummaryResponse":
        return cls(
            status=summary.status.value,
            payment_count=summary.payment_count,
            currency_totals=[
                CurrencyReconciliationTotalResponse.from_result(total)
                for total in summary.currency_totals
            ],
            matched_count=summary.matched_count,
            missing_count=summary.missing_count,
            duplicated_count=summary.duplicated_count,
            amount_mismatched_count=summary.amount_mismatched_count,
            ledger_mismatch_count=summary.ledger_mismatch_count,
            projection_mismatch_count=summary.projection_mismatch_count,
        )


class CurrencyReconciliationTotalResponse(BaseModel):
    """Summary amounts kept separate for each currency."""

    currency: str
    expected_settlement_total: int
    observed_settlement_total: int
    net_discrepancy: int

    @classmethod
    def from_result(
        cls,
        total: CurrencyReconciliationTotal,
    ) -> "CurrencyReconciliationTotalResponse":
        return cls(
            currency=total.currency,
            expected_settlement_total=total.expected_settlement_total,
            observed_settlement_total=total.observed_settlement_total,
            net_discrepancy=total.net_discrepancy,
        )


class ReconciliationReportResponse(BaseModel):
    """Stable API form of a read-only reconciliation report."""

    settlement_batch_id: str
    cutoff: datetime
    summary: ReconciliationSummaryResponse
    items: list[ReconciliationItemResponse]

    @classmethod
    def from_result(
        cls,
        report: ReconciliationReport,
    ) -> "ReconciliationReportResponse":
        return cls(
            settlement_batch_id=report.batch_id,
            cutoff=_as_utc(report.cutoff),
            summary=ReconciliationSummaryResponse.from_result(report.summary),
            items=[
                ReconciliationItemResponse.from_result(item) for item in report.items
            ],
        )
