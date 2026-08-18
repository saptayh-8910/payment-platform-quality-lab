"""Transactional payment lifecycle service."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    PaymentOperation,
    PaymentState,
    PaymentStatus,
    authorize,
    cancel,
    capture,
    refund,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
)


class PaymentNotFoundError(LookupError):
    """Requested payment does not exist."""


class IdempotencyConflictError(RuntimeError):
    """Idempotency key was reused for a different request."""


@dataclass(frozen=True, slots=True)
class AuthorizationCommand:
    """Validated inputs required to authorize a payment."""

    merchant_reference: str
    amount: int
    currency: Currency
    payment_method_token: AuthorizationDecision

    def fingerprint(self) -> str:
        """Return a stable digest without storing the synthetic token."""
        payload = {
            "amount": self.amount,
            "currency": self.currency.value,
            "merchant_reference": self.merchant_reference,
            "payment_method_token": self.payment_method_token.value,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorizationOutcome:
    """Persisted payment and whether it came from an idempotent replay."""

    payment: PaymentRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class LifecycleCommand:
    """Inputs that identify a state-changing payment operation."""

    payment_id: str
    operation: PaymentOperation
    amount: int | None = None

    def fingerprint(self) -> str:
        """Return a stable digest for idempotency conflict detection."""
        payload = {
            "amount": self.amount,
            "operation": self.operation.value,
            "payment_id": self.payment_id,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class LifecycleOutcome:
    """Persisted lifecycle result and whether it was replayed."""

    payment: PaymentRecord
    replayed: bool


def _find_idempotent_payment(
    session: Session,
    *,
    idempotency_key: str,
    fingerprint: str,
) -> PaymentRecord | None:
    """Return a prior payment result or reject conflicting key reuse."""
    existing = session.get(IdempotencyRecord, idempotency_key)
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflictError
    payment = session.get(PaymentRecord, existing.payment_id)
    if payment is None:  # pragma: no cover - protected by foreign key design
        raise PaymentNotFoundError(existing.payment_id)
    return payment


def authorize_payment(
    session: Session,
    *,
    command: AuthorizationCommand,
    idempotency_key: str,
) -> AuthorizationOutcome:
    """Create one authorization outcome atomically or replay the original."""
    fingerprint = command.fingerprint()
    payment = _find_idempotent_payment(
        session,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if payment is not None:
        return AuthorizationOutcome(payment=payment, replayed=True)

    result = authorize(command.amount, command.payment_method_token)
    now = datetime.now(UTC)
    payment = PaymentRecord(
        id=f"pay_{uuid4().hex}",
        merchant_reference=command.merchant_reference,
        amount=command.amount,
        currency=command.currency.value,
        status=result.status.value,
        authorized_amount=result.authorized_amount,
        captured_amount=0,
        refunded_amount=0,
        version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(payment)
    # Allocate the parent row before dependent records while retaining a single
    # transaction and commit for the complete financial outcome.
    session.flush()

    if result.authorized_amount:
        session.add(
            LedgerEntryRecord(
                id=f"led_{uuid4().hex}",
                payment_id=payment.id,
                operation="AUTHORIZATION",
                amount=result.authorized_amount,
                currency=command.currency.value,
                created_at=now,
            )
        )

    session.add(
        IdempotencyRecord(
            key=idempotency_key,
            request_fingerprint=fingerprint,
            operation="AUTHORIZE",
            payment_id=payment.id,
            created_at=now,
        )
    )
    session.commit()
    return AuthorizationOutcome(payment=payment, replayed=False)


def _payment_state(payment: PaymentRecord) -> PaymentState:
    """Map the persisted aggregate into the pure lifecycle model."""
    return PaymentState(
        status=PaymentStatus(payment.status),
        authorized_amount=payment.authorized_amount,
        captured_amount=payment.captured_amount,
        refunded_amount=payment.refunded_amount,
    )


def _apply_lifecycle_operation(
    session: Session,
    *,
    command: LifecycleCommand,
    idempotency_key: str,
) -> LifecycleOutcome:
    """Apply one lifecycle transition and ledger effect atomically."""
    fingerprint = command.fingerprint()
    replayed_payment = _find_idempotent_payment(
        session,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if replayed_payment is not None:
        return LifecycleOutcome(payment=replayed_payment, replayed=True)

    payment = get_payment(session, command.payment_id)
    current_state = _payment_state(payment)

    if command.operation is PaymentOperation.CAPTURE:
        next_state = capture(current_state)
        ledger_amount = next_state.captured_amount - current_state.captured_amount
    elif command.operation is PaymentOperation.CANCEL:
        next_state = cancel(current_state)
        ledger_amount = current_state.authorized_amount
    elif command.operation is PaymentOperation.REFUND and command.amount is not None:
        next_state = refund(current_state, command.amount)
        ledger_amount = command.amount
    else:  # pragma: no cover - commands are constructed by public service functions
        raise ValueError("Unsupported lifecycle operation")

    now = datetime.now(UTC)
    payment.status = next_state.status.value
    payment.authorized_amount = next_state.authorized_amount
    payment.captured_amount = next_state.captured_amount
    payment.refunded_amount = next_state.refunded_amount
    payment.version += 1
    payment.updated_at = now

    session.add(
        LedgerEntryRecord(
            id=f"led_{uuid4().hex}",
            payment_id=payment.id,
            operation=command.operation.value,
            amount=ledger_amount,
            currency=payment.currency,
            created_at=now,
        )
    )
    session.add(
        IdempotencyRecord(
            key=idempotency_key,
            request_fingerprint=fingerprint,
            operation=command.operation.value,
            payment_id=payment.id,
            created_at=now,
        )
    )
    session.commit()
    return LifecycleOutcome(payment=payment, replayed=False)


def capture_payment(
    session: Session,
    *,
    payment_id: str,
    idempotency_key: str,
) -> LifecycleOutcome:
    """Capture the full authorization exactly once."""
    return _apply_lifecycle_operation(
        session,
        command=LifecycleCommand(
            payment_id=payment_id,
            operation=PaymentOperation.CAPTURE,
        ),
        idempotency_key=idempotency_key,
    )


def cancel_payment(
    session: Session,
    *,
    payment_id: str,
    idempotency_key: str,
) -> LifecycleOutcome:
    """Cancel an uncaptured authorization exactly once."""
    return _apply_lifecycle_operation(
        session,
        command=LifecycleCommand(
            payment_id=payment_id,
            operation=PaymentOperation.CANCEL,
        ),
        idempotency_key=idempotency_key,
    )


def refund_payment(
    session: Session,
    *,
    payment_id: str,
    amount: int,
    idempotency_key: str,
) -> LifecycleOutcome:
    """Refund captured funds exactly once."""
    return _apply_lifecycle_operation(
        session,
        command=LifecycleCommand(
            payment_id=payment_id,
            operation=PaymentOperation.REFUND,
            amount=amount,
        ),
        idempotency_key=idempotency_key,
    )


def get_payment(session: Session, payment_id: str) -> PaymentRecord:
    """Load a payment or raise a domain-facing not-found error."""
    payment = session.get(PaymentRecord, payment_id)
    if payment is None:
        raise PaymentNotFoundError(payment_id)
    return payment


def get_ledger_entries(session: Session, payment_id: str) -> list[LedgerEntryRecord]:
    """Load the immutable ledger entries associated with a payment."""
    get_payment(session, payment_id)
    statement = (
        select(LedgerEntryRecord)
        .where(LedgerEntryRecord.payment_id == payment_id)
        .order_by(LedgerEntryRecord.created_at, LedgerEntryRecord.id)
    )
    return list(session.scalars(statement))
