"""Transactional payment lifecycle service."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

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
from payment_quality_lab.services.webhooks import (
    WebhookEventType,
    create_outbox_event,
)


class PaymentNotFoundError(LookupError):
    """Requested payment does not exist."""


class IdempotencyConflictError(RuntimeError):
    """Idempotency key was reused for a different request."""


class ConcurrentPaymentUpdateError(RuntimeError):
    """A stale payment version attempted to overwrite a newer result."""


class FailureInjectionDisabledError(RuntimeError):
    """A test-only failure control was requested outside demonstration mode."""


class FailurePoint(StrEnum):
    """Deterministic transaction boundaries available to reliability tests."""

    BEFORE_COMMIT = "before_commit"
    AFTER_COMMIT = "after_commit"


class SimulatedPaymentTimeoutError(TimeoutError):
    """A deterministic timeout raised at a selected transaction boundary."""

    def __init__(self, point: FailurePoint) -> None:
        self.point = point
        super().__init__(f"Simulated payment timeout at {point.value}")


@dataclass(frozen=True, slots=True)
class PaymentSnapshot:
    """Immutable payment representation stored for exact idempotent replay."""

    id: str
    merchant_reference: str
    amount: int
    currency: str
    status: str
    authorized_amount: int
    captured_amount: int
    refunded_amount: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_payment(cls, payment: PaymentRecord) -> "PaymentSnapshot":
        """Copy an ORM payment without retaining mutable session state."""
        return cls(
            id=payment.id,
            merchant_reference=payment.merchant_reference,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            authorized_amount=payment.authorized_amount,
            captured_amount=payment.captured_amount,
            refunded_amount=payment.refunded_amount,
            version=payment.version,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    def serialize(self) -> str:
        """Return a stable JSON representation for persistence."""
        return json.dumps(
            {
                "amount": self.amount,
                "authorized_amount": self.authorized_amount,
                "captured_amount": self.captured_amount,
                "created_at": self.created_at.isoformat(),
                "currency": self.currency,
                "id": self.id,
                "merchant_reference": self.merchant_reference,
                "refunded_amount": self.refunded_amount,
                "status": self.status,
                "updated_at": self.updated_at.isoformat(),
                "version": self.version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def deserialize(cls, payload: str) -> "PaymentSnapshot":
        """Restore a persisted idempotency response snapshot."""
        values = json.loads(payload)
        return cls(
            id=str(values["id"]),
            merchant_reference=str(values["merchant_reference"]),
            amount=int(values["amount"]),
            currency=str(values["currency"]),
            status=str(values["status"]),
            authorized_amount=int(values["authorized_amount"]),
            captured_amount=int(values["captured_amount"]),
            refunded_amount=int(values["refunded_amount"]),
            version=int(values["version"]),
            created_at=datetime.fromisoformat(values["created_at"]),
            updated_at=datetime.fromisoformat(values["updated_at"]),
        )


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

    payment: PaymentRecord | PaymentSnapshot
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

    payment: PaymentRecord | PaymentSnapshot
    replayed: bool


def _find_idempotent_snapshot(
    session: Session,
    *,
    idempotency_key: str,
    fingerprint: str,
) -> PaymentSnapshot | None:
    """Return an immutable prior result or reject conflicting key reuse."""
    existing = session.get(IdempotencyRecord, idempotency_key)
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflictError
    if existing.response_snapshot is None:  # pragma: no cover - never committed
        raise RuntimeError("Idempotency record has no completed response")
    return PaymentSnapshot.deserialize(existing.response_snapshot)


def _claim_idempotency_key(
    session: Session,
    *,
    idempotency_key: str,
    fingerprint: str,
    operation: str,
) -> tuple[IdempotencyRecord | None, PaymentSnapshot | None]:
    """Claim a key before mutation or replay a concurrently committed result."""
    replay = _find_idempotent_snapshot(
        session,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return None, replay

    claim = IdempotencyRecord(
        key=idempotency_key,
        request_fingerprint=fingerprint,
        operation=operation,
        payment_id=None,
        response_snapshot=None,
        created_at=datetime.now(UTC),
    )
    session.add(claim)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        replay = _find_idempotent_snapshot(
            session,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        if replay is None:  # pragma: no cover - defensive unexpected constraint
            raise
        return None, replay
    return claim, None


def _commit_financial_outcome(
    session: Session,
    *,
    claim: IdempotencyRecord,
    payment: PaymentRecord,
    event_type: WebhookEventType,
    failure_point: FailurePoint | None,
) -> None:
    """Commit financial state, response snapshot, and outbox event atomically."""
    try:
        session.flush()
        create_outbox_event(session, payment=payment, event_type=event_type)
        claim.payment_id = payment.id
        claim.response_snapshot = PaymentSnapshot.from_payment(payment).serialize()
        session.flush()
        if failure_point is FailurePoint.BEFORE_COMMIT:
            raise SimulatedPaymentTimeoutError(failure_point)
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise ConcurrentPaymentUpdateError(payment.id) from error
    except Exception:
        session.rollback()
        raise

    if failure_point is FailurePoint.AFTER_COMMIT:
        raise SimulatedPaymentTimeoutError(failure_point)


def authorize_payment(
    session: Session,
    *,
    command: AuthorizationCommand,
    idempotency_key: str,
    failure_point: FailurePoint | None = None,
) -> AuthorizationOutcome:
    """Create one authorization outcome atomically or replay the original."""
    fingerprint = command.fingerprint()
    claim, replay = _claim_idempotency_key(
        session,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        operation="AUTHORIZE",
    )
    if replay is not None:
        return AuthorizationOutcome(payment=replay, replayed=True)
    assert claim is not None

    try:
        return _execute_claimed_authorization(
            session,
            command=command,
            claim=claim,
            failure_point=failure_point,
        )
    except Exception:
        if session.in_transaction():
            session.rollback()
        raise


def _execute_claimed_authorization(
    session: Session,
    *,
    command: AuthorizationCommand,
    claim: IdempotencyRecord,
    failure_point: FailurePoint | None,
) -> AuthorizationOutcome:
    """Validate and commit an authorization after its key is claimed."""

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

    _commit_financial_outcome(
        session,
        claim=claim,
        payment=payment,
        event_type=(
            WebhookEventType.AUTHORIZED
            if result.status is PaymentStatus.AUTHORIZED
            else WebhookEventType.DECLINED
        ),
        failure_point=failure_point,
    )
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
    failure_point: FailurePoint | None,
) -> LifecycleOutcome:
    """Apply one lifecycle transition and ledger effect atomically."""
    fingerprint = command.fingerprint()
    claim, replay = _claim_idempotency_key(
        session,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        operation=command.operation.value,
    )
    if replay is not None:
        return LifecycleOutcome(payment=replay, replayed=True)
    assert claim is not None

    try:
        return _execute_claimed_lifecycle_operation(
            session,
            command=command,
            claim=claim,
            failure_point=failure_point,
        )
    except Exception:
        if session.in_transaction():
            session.rollback()
        raise


def _execute_claimed_lifecycle_operation(
    session: Session,
    *,
    command: LifecycleCommand,
    claim: IdempotencyRecord,
    failure_point: FailurePoint | None,
) -> LifecycleOutcome:
    """Validate and commit an operation after its idempotency claim is held."""

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
    _commit_financial_outcome(
        session,
        claim=claim,
        payment=payment,
        event_type={
            PaymentOperation.CAPTURE: WebhookEventType.CAPTURED,
            PaymentOperation.CANCEL: WebhookEventType.CANCELLED,
            PaymentOperation.REFUND: WebhookEventType.REFUNDED,
        }[command.operation],
        failure_point=failure_point,
    )
    return LifecycleOutcome(payment=payment, replayed=False)


def capture_payment(
    session: Session,
    *,
    payment_id: str,
    idempotency_key: str,
    failure_point: FailurePoint | None = None,
) -> LifecycleOutcome:
    """Capture the full authorization exactly once."""
    return _apply_lifecycle_operation(
        session,
        command=LifecycleCommand(
            payment_id=payment_id,
            operation=PaymentOperation.CAPTURE,
        ),
        idempotency_key=idempotency_key,
        failure_point=failure_point,
    )


def cancel_payment(
    session: Session,
    *,
    payment_id: str,
    idempotency_key: str,
    failure_point: FailurePoint | None = None,
) -> LifecycleOutcome:
    """Cancel an uncaptured authorization exactly once."""
    return _apply_lifecycle_operation(
        session,
        command=LifecycleCommand(
            payment_id=payment_id,
            operation=PaymentOperation.CANCEL,
        ),
        idempotency_key=idempotency_key,
        failure_point=failure_point,
    )


def refund_payment(
    session: Session,
    *,
    payment_id: str,
    amount: int,
    idempotency_key: str,
    failure_point: FailurePoint | None = None,
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
        failure_point=failure_point,
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
