"""Pure lifecycle and financial rules for the payment domain."""

from dataclasses import dataclass
from enum import StrEnum


class Currency(StrEnum):
    """Currencies supported by the MVP."""

    USD = "USD"
    JPY = "JPY"


class PaymentStatus(StrEnum):
    """Supported payment lifecycle states."""

    AUTHORIZED = "AUTHORIZED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    DECLINED = "DECLINED"
    CAPTURED = "CAPTURED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AuthorizationDecision(StrEnum):
    """Deterministic test-token outcomes."""

    APPROVE = "tok_approved"
    DECLINE = "tok_declined"
    DECLINE_INSUFFICIENT_FUNDS = "tok_declined_insufficient_funds"
    DECLINE_LIMIT_EXCEEDED = "tok_declined_limit_exceeded"
    DECLINE_EXPIRED = "tok_declined_expired"
    DECLINE_VERIFICATION = "tok_declined_verification"
    DECLINE_INVALID = "tok_declined_invalid"
    DECLINE_UNKNOWN = "tok_declined_unknown"


class DelayedPaymentDecision(StrEnum):
    """Provider-neutral simulator input for delayed confirmation."""

    AWAIT_CONFIRMATION = "tok_awaiting_confirmation"


class PaymentFlow(StrEnum):
    """How a payment reaches its financial outcome."""

    SYNCHRONOUS = "SYNCHRONOUS"
    ASYNCHRONOUS_CONFIRMATION = "ASYNCHRONOUS_CONFIRMATION"


type PaymentMethodDecision = AuthorizationDecision | DelayedPaymentDecision


class DeclineReason(StrEnum):
    """Stable provider-neutral explanations for declined authorizations."""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    LIMIT_EXCEEDED = "limit_exceeded"
    EXPIRED_PAYMENT_METHOD = "expired_payment_method"
    VERIFICATION_FAILED = "verification_failed"
    INVALID_PAYMENT_METHOD = "invalid_payment_method"
    UNKNOWN = "unknown"


DECLINE_REASON_BY_DECISION: dict[AuthorizationDecision, DeclineReason] = {
    AuthorizationDecision.DECLINE: DeclineReason.UNKNOWN,
    AuthorizationDecision.DECLINE_INSUFFICIENT_FUNDS: (
        DeclineReason.INSUFFICIENT_FUNDS
    ),
    AuthorizationDecision.DECLINE_LIMIT_EXCEEDED: DeclineReason.LIMIT_EXCEEDED,
    AuthorizationDecision.DECLINE_EXPIRED: DeclineReason.EXPIRED_PAYMENT_METHOD,
    AuthorizationDecision.DECLINE_VERIFICATION: DeclineReason.VERIFICATION_FAILED,
    AuthorizationDecision.DECLINE_INVALID: DeclineReason.INVALID_PAYMENT_METHOD,
    AuthorizationDecision.DECLINE_UNKNOWN: DeclineReason.UNKNOWN,
}


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Result of applying the authorization decision."""

    status: PaymentStatus
    authorized_amount: int
    decline_reason: DeclineReason | None


class PaymentOperation(StrEnum):
    """State-changing operations supported by the simulator."""

    AUTHORIZE = "AUTHORIZE"
    CAPTURE = "CAPTURE"
    CANCEL = "CANCEL"
    REFUND = "REFUND"
    CONFIRMATION_CAPTURE = "CONFIRMATION_CAPTURE"
    EXPIRE = "EXPIRE"


class InvalidPaymentTransitionError(ValueError):
    """Operation is not valid from the payment's current state."""

    def __init__(self, operation: PaymentOperation, status: PaymentStatus) -> None:
        self.operation = operation
        self.status = status
        super().__init__(f"Cannot {operation.value} payment in {status.value} state")


class RefundAmountExceededError(ValueError):
    """Requested refund is greater than the remaining captured balance."""

    def __init__(self, requested: int, available: int) -> None:
        self.requested = requested
        self.available = available
        super().__init__(
            f"Refund amount {requested} exceeds refundable amount {available}"
        )


@dataclass(frozen=True, slots=True)
class PaymentState:
    """Financial state used by pure lifecycle operations."""

    status: PaymentStatus
    authorized_amount: int
    captured_amount: int
    refunded_amount: int

    def __post_init__(self) -> None:
        if (
            min(
                self.authorized_amount,
                self.captured_amount,
                self.refunded_amount,
            )
            < 0
        ):
            raise ValueError("Payment balances cannot be negative")
        if self.captured_amount > self.authorized_amount:
            raise ValueError("Captured amount cannot exceed authorized amount")
        if self.refunded_amount > self.captured_amount:
            raise ValueError("Refunded amount cannot exceed captured amount")

    @property
    def refundable_amount(self) -> int:
        """Return the captured balance not yet refunded."""
        return self.captured_amount - self.refunded_amount


def authorize(amount: int, decision: AuthorizationDecision) -> AuthorizationResult:
    """Authorize or decline a validated positive payment amount."""
    if amount <= 0:
        raise ValueError("Payment amount must be positive")

    if decision is AuthorizationDecision.APPROVE:
        return AuthorizationResult(
            status=PaymentStatus.AUTHORIZED,
            authorized_amount=amount,
            decline_reason=None,
        )

    return AuthorizationResult(
        status=PaymentStatus.DECLINED,
        authorized_amount=0,
        decline_reason=DECLINE_REASON_BY_DECISION[decision],
    )


def capture(state: PaymentState) -> PaymentState:
    """Capture the full amount of an authorized payment."""
    if state.status is not PaymentStatus.AUTHORIZED:
        raise InvalidPaymentTransitionError(PaymentOperation.CAPTURE, state.status)

    return PaymentState(
        status=PaymentStatus.CAPTURED,
        authorized_amount=state.authorized_amount,
        captured_amount=state.authorized_amount,
        refunded_amount=0,
    )


def capture_confirmation(state: PaymentState, amount: int) -> PaymentState:
    """Atomically recognize and capture a confirmed delayed payment."""
    if state.status is not PaymentStatus.AWAITING_PAYMENT:
        raise InvalidPaymentTransitionError(
            PaymentOperation.CONFIRMATION_CAPTURE,
            state.status,
        )
    if amount <= 0:
        raise ValueError("Confirmed amount must be positive")

    return PaymentState(
        status=PaymentStatus.CAPTURED,
        authorized_amount=amount,
        captured_amount=amount,
        refunded_amount=0,
    )


def expire(state: PaymentState) -> PaymentState:
    """Expire a delayed payment without creating a financial effect."""
    if state.status is not PaymentStatus.AWAITING_PAYMENT:
        raise InvalidPaymentTransitionError(PaymentOperation.EXPIRE, state.status)

    return PaymentState(
        status=PaymentStatus.EXPIRED,
        authorized_amount=state.authorized_amount,
        captured_amount=state.captured_amount,
        refunded_amount=state.refunded_amount,
    )


def cancel(state: PaymentState) -> PaymentState:
    """Cancel an authorization before capture."""
    if state.status is not PaymentStatus.AUTHORIZED:
        raise InvalidPaymentTransitionError(PaymentOperation.CANCEL, state.status)

    return PaymentState(
        status=PaymentStatus.CANCELLED,
        authorized_amount=state.authorized_amount,
        captured_amount=0,
        refunded_amount=0,
    )


def refund(state: PaymentState, amount: int) -> PaymentState:
    """Apply a positive partial or full refund to captured funds."""
    if state.status not in {
        PaymentStatus.CAPTURED,
        PaymentStatus.PARTIALLY_REFUNDED,
    }:
        raise InvalidPaymentTransitionError(PaymentOperation.REFUND, state.status)
    if amount <= 0:
        raise ValueError("Refund amount must be positive")
    if amount > state.refundable_amount:
        raise RefundAmountExceededError(amount, state.refundable_amount)

    refunded_amount = state.refunded_amount + amount
    next_status = (
        PaymentStatus.REFUNDED
        if refunded_amount == state.captured_amount
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    return PaymentState(
        status=next_status,
        authorized_amount=state.authorized_amount,
        captured_amount=state.captured_amount,
        refunded_amount=refunded_amount,
    )
