"""Persistence models for payments, ledger entries, and idempotency records."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from payment_quality_lab.persistence.database import Base


class PaymentRecord(Base):
    """Persisted payment aggregate."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    merchant_reference: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), index=True)
    authorized_amount: Mapped[int] = mapped_column(Integer, default=0)
    captured_amount: Mapped[int] = mapped_column(Integer, default=0)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    ledger_entries: Mapped[list["LedgerEntryRecord"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class LedgerEntryRecord(Base):
    """Immutable financial effect recorded for a payment."""

    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
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
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
