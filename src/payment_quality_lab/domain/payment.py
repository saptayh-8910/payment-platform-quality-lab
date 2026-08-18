"""Pure authorization rules for the payment domain."""

from dataclasses import dataclass
from enum import StrEnum


class Currency(StrEnum):
    """Currencies supported by the MVP."""

    USD = "USD"
    JPY = "JPY"


class PaymentStatus(StrEnum):
    """Payment states introduced by the authorization slice."""

    AUTHORIZED = "AUTHORIZED"
    DECLINED = "DECLINED"


class AuthorizationDecision(StrEnum):
    """Deterministic test-token outcomes."""

    APPROVE = "tok_approved"
    DECLINE = "tok_declined"


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Result of applying the authorization decision."""

    status: PaymentStatus
    authorized_amount: int


def authorize(amount: int, decision: AuthorizationDecision) -> AuthorizationResult:
    """Authorize or decline a validated positive payment amount."""
    if amount <= 0:
        raise ValueError("Payment amount must be positive")

    if decision is AuthorizationDecision.APPROVE:
        return AuthorizationResult(
            status=PaymentStatus.AUTHORIZED,
            authorized_amount=amount,
        )

    return AuthorizationResult(
        status=PaymentStatus.DECLINED,
        authorized_amount=0,
    )
