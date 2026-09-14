"""SQLite transaction ordering shared by delayed-payment operations."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from payment_quality_lab.persistence.models import (
    ConfirmationReceiptRecord,
    PaymentRecord,
)


def begin_coordinated_write(session: Session) -> None:
    """Reserve the writer before decisions in a clean, dedicated session."""
    if session.new or session.dirty or session.deleted:
        raise ValueError("Confirmation operations require a clean session")
    if session.get_bind().dialect.name != "sqlite":
        raise ValueError("Confirmation coordination currently supports SQLite only")
    session.rollback()
    session.expire_all()
    session.execute(text("BEGIN IMMEDIATE"))


def protecting_receipt_exists():
    """Correlated predicate shared by expiry and cancellation."""
    return (
        select(ConfirmationReceiptRecord.confirmation_id)
        .where(
            ConfirmationReceiptRecord.payment_reference
            == PaymentRecord.payment_reference,
            ConfirmationReceiptRecord.completed.is_(False),
            ConfirmationReceiptRecord.amount == PaymentRecord.amount,
            ConfirmationReceiptRecord.currency == PaymentRecord.currency,
            ConfirmationReceiptRecord.received_at < PaymentRecord.expires_at,
        )
        .exists()
    )


def has_protecting_receipt(session: Session, payment: PaymentRecord) -> bool:
    return bool(
        session.scalar(
            select(protecting_receipt_exists())
            .select_from(PaymentRecord)
            .where(PaymentRecord.id == payment.id)
        )
    )
