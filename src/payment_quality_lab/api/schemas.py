"""Public API request and response schemas."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    PaymentStatus,
)
from payment_quality_lab.persistence.models import LedgerEntryRecord, PaymentRecord
from payment_quality_lab.services.payments import PaymentSnapshot


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
