"""Public API request and response schemas."""

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    PaymentStatus,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    WebhookDeliveryAttemptRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.payments import PaymentSnapshot
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
