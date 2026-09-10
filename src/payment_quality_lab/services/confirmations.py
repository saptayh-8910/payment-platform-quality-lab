"""Authenticated asynchronous payment-confirmation processing."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from payment_quality_lab.domain.payment import (
    Currency,
    PaymentState,
    PaymentStatus,
    capture_confirmation,
    expire,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    PaymentConfirmationRecord,
    PaymentRecord,
)
from payment_quality_lab.services.payments import ConcurrentPaymentUpdateError
from payment_quality_lab.services.webhooks import (
    InvalidWebhookSignatureError,
    WebhookEventType,
    create_outbox_event,
    verify_webhook_signature,
)

SAFE_CONFIRMATION_RESPONSE = '{"accepted":true}'
DEFAULT_EXPIRY_BATCH_SIZE = 100
MAX_EXPIRY_BATCH_SIZE = 1_000


class ConfirmationDisposition(StrEnum):
    """Internal result retained for investigation and reconciliation."""

    APPLIED = "applied"
    LATE = "late"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    UNKNOWN_REFERENCE = "unknown_reference"
    ALREADY_RESOLVED = "already_resolved"


class InvalidConfirmationSignatureError(ValueError):
    """Confirmation signature is absent, malformed, stale, or incorrect."""


class InvalidConfirmationPayloadError(ValueError):
    """Authenticated body does not match the confirmation contract."""


class ConfirmationIdConflictError(RuntimeError):
    """A confirmation identity was reused with different content."""


class ConfirmationNotFoundError(LookupError):
    """Requested internal confirmation evidence does not exist."""


@dataclass(frozen=True, slots=True)
class ConfirmationCommand:
    """Validated fields supplied by the synthetic confirmation sender."""

    confirmation_id: str
    payment_reference: str
    amount: int
    currency: Currency

    def fingerprint(self) -> str:
        """Return a stable content digest for identity conflict detection."""
        canonical = json.dumps(
            {
                "amount": self.amount,
                "confirmation_id": self.confirmation_id,
                "currency": self.currency.value,
                "payment_reference": self.payment_reference,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ConfirmationOutcome:
    """Safe processing result and internal durable evidence."""

    confirmation: PaymentConfirmationRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExpiryRunResult:
    """Observable summary of one bounded scheduled-expiry transaction."""

    expired_payment_ids: tuple[str, ...]

    @property
    def expired_count(self) -> int:
        """Return the number of payments expired by this invocation."""
        return len(self.expired_payment_ids)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def read_confirmation_clock(clock: Callable[[], datetime]) -> datetime:
    """Read one trusted, timezone-aware receipt time."""
    return _require_aware_utc(clock(), field_name="Confirmation clock")


def verify_confirmation_signature(
    payload: bytes,
    *,
    signature_header: str | None,
    secret: str,
    received_at: datetime,
) -> None:
    """Apply the shared HMAC format at the confirmation trust boundary."""
    if not signature_header:
        raise InvalidConfirmationSignatureError("Missing confirmation signature")
    try:
        verify_webhook_signature(
            payload,
            signature_header=signature_header,
            secret=secret,
            now=received_at,
        )
    except InvalidWebhookSignatureError as error:
        raise InvalidConfirmationSignatureError(
            "Confirmation signature could not be verified"
        ) from error


def _existing_outcome(
    session: Session,
    *,
    confirmation_id: str,
    fingerprint: str,
) -> ConfirmationOutcome | None:
    existing = session.get(PaymentConfirmationRecord, confirmation_id)
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise ConfirmationIdConflictError
    return ConfirmationOutcome(confirmation=existing, replayed=True)


def _payment_by_reference(
    session: Session,
    payment_reference: str,
) -> PaymentRecord | None:
    return session.scalar(
        select(PaymentRecord).where(
            PaymentRecord.payment_reference == payment_reference
        )
    )


def _payment_state(payment: PaymentRecord) -> PaymentState:
    return PaymentState(
        status=PaymentStatus(payment.status),
        authorized_amount=payment.authorized_amount,
        captured_amount=payment.captured_amount,
        refunded_amount=payment.refunded_amount,
    )


def _apply_expiry_transition(
    session: Session,
    *,
    payment: PaymentRecord,
    occurred_at: datetime,
) -> None:
    """Stage the single shared expiry transition and lifecycle event."""
    next_state = expire(_payment_state(payment))
    payment.status = next_state.status.value
    payment.authorized_amount = next_state.authorized_amount
    payment.captured_amount = next_state.captured_amount
    payment.refunded_amount = next_state.refunded_amount
    payment.updated_at = occurred_at
    session.flush()
    create_outbox_event(
        session,
        payment=payment,
        event_type=WebhookEventType.EXPIRED,
    )


def _classify(
    payment: PaymentRecord | None,
    *,
    command: ConfirmationCommand,
    received_at: datetime,
) -> ConfirmationDisposition:
    if payment is None:
        return ConfirmationDisposition.UNKNOWN_REFERENCE
    status = PaymentStatus(payment.status)
    if status is PaymentStatus.EXPIRED:
        return ConfirmationDisposition.LATE
    if status is not PaymentStatus.AWAITING_PAYMENT:
        return ConfirmationDisposition.ALREADY_RESOLVED
    assert payment.expires_at is not None
    if received_at >= _as_utc(payment.expires_at):
        return ConfirmationDisposition.LATE
    if command.amount != payment.amount:
        return ConfirmationDisposition.AMOUNT_MISMATCH
    if command.currency.value != payment.currency:
        return ConfirmationDisposition.CURRENCY_MISMATCH
    return ConfirmationDisposition.APPLIED


def _apply_disposition(
    session: Session,
    *,
    payment: PaymentRecord | None,
    command: ConfirmationCommand,
    disposition: ConfirmationDisposition,
    received_at: datetime,
) -> None:
    if payment is None:
        return
    if disposition is ConfirmationDisposition.APPLIED:
        next_state = capture_confirmation(_payment_state(payment), command.amount)
        payment.status = next_state.status.value
        payment.authorized_amount = next_state.authorized_amount
        payment.captured_amount = next_state.captured_amount
        payment.refunded_amount = next_state.refunded_amount
        payment.updated_at = received_at
        session.add(
            LedgerEntryRecord(
                id=f"led_{uuid4().hex}",
                payment_id=payment.id,
                operation="CONFIRMATION_CAPTURE",
                amount=command.amount,
                currency=payment.currency,
                created_at=received_at,
            )
        )
        session.flush()
        create_outbox_event(
            session,
            payment=payment,
            event_type=WebhookEventType.CAPTURED,
        )
    elif (
        disposition is ConfirmationDisposition.LATE
        and PaymentStatus(payment.status) is PaymentStatus.AWAITING_PAYMENT
    ):
        _apply_expiry_transition(
            session,
            payment=payment,
            occurred_at=received_at,
        )


def process_confirmation(
    session: Session,
    *,
    command: ConfirmationCommand,
    received_at: datetime,
) -> ConfirmationOutcome:
    """Classify and commit one authenticated confirmation atomically."""
    received_at = _require_aware_utc(received_at, field_name="received_at")
    fingerprint = command.fingerprint()
    replay = _existing_outcome(
        session,
        confirmation_id=command.confirmation_id,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay

    payment = _payment_by_reference(session, command.payment_reference)
    disposition = _classify(
        payment,
        command=command,
        received_at=received_at,
    )
    confirmation = PaymentConfirmationRecord(
        confirmation_id=command.confirmation_id,
        request_fingerprint=fingerprint,
        payment_reference=command.payment_reference,
        amount=command.amount,
        currency=command.currency.value,
        received_at=received_at,
        disposition=disposition.value,
        payment_id=payment.id if payment is not None else None,
        response_snapshot=SAFE_CONFIRMATION_RESPONSE,
    )
    session.add(confirmation)

    try:
        _apply_disposition(
            session,
            payment=payment,
            command=command,
            disposition=disposition,
            received_at=received_at,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = _existing_outcome(
            session,
            confirmation_id=command.confirmation_id,
            fingerprint=fingerprint,
        )
        if replay is None:
            raise
        return replay
    except StaleDataError as error:
        session.rollback()
        payment_id = payment.id if payment is not None else command.payment_reference
        raise ConcurrentPaymentUpdateError(payment_id) from error
    except Exception:
        session.rollback()
        raise

    return ConfirmationOutcome(confirmation=confirmation, replayed=False)


def expire_due_payments(
    session: Session,
    *,
    now: datetime,
    limit: int = DEFAULT_EXPIRY_BATCH_SIZE,
) -> ExpiryRunResult:
    """Expire one bounded, deterministic batch in a single transaction."""
    current = _require_aware_utc(now, field_name="now")
    if not 1 <= limit <= MAX_EXPIRY_BATCH_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_EXPIRY_BATCH_SIZE}")

    statement = (
        select(PaymentRecord)
        .where(
            PaymentRecord.status == PaymentStatus.AWAITING_PAYMENT.value,
            PaymentRecord.expires_at.is_not(None),
            PaymentRecord.expires_at <= current,
        )
        .order_by(PaymentRecord.expires_at, PaymentRecord.id)
        .limit(limit)
    )
    due_payments = list(session.scalars(statement))
    active_payment_id = "scheduled-expiry"

    try:
        for payment in due_payments:
            active_payment_id = payment.id
            _apply_expiry_transition(
                session,
                payment=payment,
                occurred_at=current,
            )
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise ConcurrentPaymentUpdateError(active_payment_id) from error
    except Exception:
        session.rollback()
        raise

    return ExpiryRunResult(
        expired_payment_ids=tuple(payment.id for payment in due_payments)
    )


def get_confirmation(
    session: Session,
    confirmation_id: str,
) -> PaymentConfirmationRecord:
    """Retrieve internal confirmation evidence independently of payment state."""
    confirmation = session.get(PaymentConfirmationRecord, confirmation_id)
    if confirmation is None:
        raise ConfirmationNotFoundError(confirmation_id)
    return confirmation
