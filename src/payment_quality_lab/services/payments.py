"""Transactional payment authorization service."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    authorize,
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


def authorize_payment(
    session: Session,
    *,
    command: AuthorizationCommand,
    idempotency_key: str,
) -> AuthorizationOutcome:
    """Create one authorization outcome atomically or replay the original."""
    fingerprint = command.fingerprint()
    existing = session.get(IdempotencyRecord, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflictError
        payment = session.get(PaymentRecord, existing.payment_id)
        if payment is None:  # pragma: no cover - protected by foreign key design
            raise PaymentNotFoundError(existing.payment_id)
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


def get_payment(session: Session, payment_id: str) -> PaymentRecord:
    """Load a payment or raise a domain-facing not-found error."""
    payment = session.get(PaymentRecord, payment_id)
    if payment is None:
        raise PaymentNotFoundError(payment_id)
    return payment


def get_ledger_entries(session: Session, payment_id: str) -> list[LedgerEntryRecord]:
    """Load the immutable ledger entries associated with a payment."""
    payment = get_payment(session, payment_id)
    return list(payment.ledger_entries)
