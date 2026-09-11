"""Persistence models for payments, ledger entries, and idempotency records."""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from payment_quality_lab.persistence.database import Base


class PaymentRecord(Base):
    """Persisted payment aggregate."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint(
            "authorized_amount >= 0 AND authorized_amount <= amount",
            name="ck_payment_authorized_within_amount",
        ),
        CheckConstraint(
            "captured_amount >= 0 AND captured_amount <= authorized_amount",
            name="ck_payment_captured_within_authorized",
        ),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= captured_amount",
            name="ck_payment_refunded_within_captured",
        ),
        CheckConstraint(
            "payment_flow IN ('SYNCHRONOUS', 'ASYNCHRONOUS_CONFIRMATION')",
            name="ck_payment_flow_supported",
        ),
        CheckConstraint(
            "(payment_flow = 'SYNCHRONOUS' AND payment_reference IS NULL "
            "AND expires_at IS NULL) OR "
            "(payment_flow = 'ASYNCHRONOUS_CONFIRMATION' "
            "AND payment_reference IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_payment_flow_metadata",
        ),
        CheckConstraint(
            "(status = 'DECLINED' AND decline_reason IS NOT NULL AND "
            "decline_reason IN ("
            "'insufficient_funds', 'limit_exceeded', 'expired_payment_method', "
            "'verification_failed', 'invalid_payment_method', 'unknown')) OR "
            "(status <> 'DECLINED' AND decline_reason IS NULL)",
            name="ck_payment_decline_reason_matches_status",
        ),
        CheckConstraint("version >= 1", name="ck_payment_version_positive"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    merchant_reference: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), index=True)
    payment_flow: Mapped[str] = mapped_column(String(32), default="SYNCHRONOUS")
    payment_reference: Mapped[str | None] = mapped_column(
        String(36), unique=True, nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decline_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    authorized_amount: Mapped[int] = mapped_column(Integer, default=0)
    captured_amount: Mapped[int] = mapped_column(Integer, default=0)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    ledger_entries: Mapped[list["LedgerEntryRecord"]] = relationship(
        back_populates="payment",
    )

    __mapper_args__: ClassVar[dict[str, object]] = {
        "version_id_col": version,
    }


class LedgerEntryRecord(Base):
    """Immutable financial effect recorded for a payment."""

    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    payment: Mapped[PaymentRecord] = relationship(back_populates="ledger_entries")


class IdempotencyRecord(Base):
    """Original outcome associated with an idempotency key."""

    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(32))
    payment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    response_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebhookEventRecord(Base):
    """Transactional outbox event for one accepted payment version."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint("aggregate_version >= 1", name="ck_webhook_version_positive"),
        CheckConstraint("attempt_count >= 0", name="ck_webhook_attempt_count"),
        UniqueConstraint(
            "payment_id",
            "aggregate_version",
            name="uq_webhook_payment_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class WebhookDeliveryAttemptRecord(Base):
    """One observable attempt to deliver an outbox event."""

    __tablename__ = "webhook_delivery_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_delivery_attempt_positive"),
        UniqueConstraint(
            "event_id",
            "attempt_number",
            name="uq_delivery_event_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="RESTRICT"),
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessedWebhookRecord(Base):
    """Consumer inbox record that prevents repeated business effects."""

    __tablename__ = "processed_webhooks"

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(40), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    payload_hash: Mapped[str] = mapped_column(String(64))
    disposition: Mapped[str] = mapped_column(String(24))
    version_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConfirmationReceiptRecord(Base):
    """Immutable accepted input and separately tracked processing completion."""

    __tablename__ = "confirmation_receipts"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_receipt_amount_positive"),
        CheckConstraint("currency IN ('JPY', 'USD')", name="ck_receipt_currency"),
    )

    confirmation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    payment_reference: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class PaymentConfirmationRecord(Base):
    """Durable, minimal evidence for one authenticated confirmation."""

    __tablename__ = "payment_confirmations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_confirmation_amount_positive"),
        CheckConstraint(
            "currency IN ('JPY', 'USD')",
            name="ck_confirmation_currency_supported",
        ),
        CheckConstraint(
            "disposition IN ("
            "'applied', 'late', 'amount_mismatch', 'currency_mismatch', "
            "'unknown_reference', 'already_resolved')",
            name="ck_confirmation_disposition_supported",
        ),
    )

    confirmation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    payment_reference: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    disposition: Mapped[str] = mapped_column(String(32), index=True)
    payment_id: Mapped[str | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    response_snapshot: Mapped[str] = mapped_column(Text)


class MerchantPaymentProjectionRecord(Base):
    """Merchant-facing payment view updated only by accepted webhooks."""

    __tablename__ = "merchant_payment_projections"

    payment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    merchant_reference: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), index=True)
    payment_flow: Mapped[str] = mapped_column(String(32), default="SYNCHRONOUS")
    payment_reference: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decline_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    authorized_amount: Mapped[int] = mapped_column(Integer)
    captured_amount: Mapped[int] = mapped_column(Integer)
    refunded_amount: Mapped[int] = mapped_column(Integer)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    last_event_id: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SettlementBatchRecord(Base):
    """One imported synthetic settlement file and its financial cutoff."""

    __tablename__ = "settlement_batches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SettlementRecord(Base):
    """External settlement row retained independently from payment state."""

    __tablename__ = "settlement_records"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_amount_positive"),
        CheckConstraint("line_number >= 1", name="ck_settlement_line_positive"),
        UniqueConstraint(
            "batch_id",
            "line_number",
            name="uq_settlement_batch_line",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("settlement_batches.id", ondelete="RESTRICT"),
        index=True,
    )
    payment_id: Mapped[str] = mapped_column(String(40), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
