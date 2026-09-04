"""Unit tests for stable idempotency request fingerprints."""

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    DelayedPaymentDecision,
)
from payment_quality_lab.services.payments import AuthorizationCommand


def command(**changes: object) -> AuthorizationCommand:
    values = {
        "merchant_reference": "order-1",
        "amount": 1000,
        "currency": Currency.JPY,
        "payment_method_token": AuthorizationDecision.APPROVE,
    }
    values.update(changes)
    return AuthorizationCommand(**values)  # type: ignore[arg-type]


def test_equivalent_commands_have_the_same_fingerprint() -> None:
    assert command().fingerprint() == command().fingerprint()


def test_financially_distinct_commands_have_different_fingerprints() -> None:
    original = command().fingerprint()

    assert command(amount=1001).fingerprint() != original
    assert command(currency=Currency.USD).fingerprint() != original
    assert command(merchant_reference="order-2").fingerprint() != original
    assert (
        command(payment_method_token=AuthorizationDecision.DECLINE).fingerprint()
        != original
    )
    assert (
        command(
            payment_method_token=DelayedPaymentDecision.AWAIT_CONFIRMATION
        ).fingerprint()
        != original
    )
