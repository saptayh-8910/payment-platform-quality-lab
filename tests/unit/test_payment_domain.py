"""Unit tests for pure payment authorization rules."""

import pytest

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    DeclineReason,
    PaymentState,
    PaymentStatus,
    authorize,
)


def test_approved_authorization_reserves_the_full_amount() -> None:
    result = authorize(2500, AuthorizationDecision.APPROVE)

    assert result.status is PaymentStatus.AUTHORIZED
    assert result.authorized_amount == 2500
    assert result.decline_reason is None


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        (AuthorizationDecision.DECLINE, DeclineReason.UNKNOWN),
        (
            AuthorizationDecision.DECLINE_INSUFFICIENT_FUNDS,
            DeclineReason.INSUFFICIENT_FUNDS,
        ),
        (
            AuthorizationDecision.DECLINE_LIMIT_EXCEEDED,
            DeclineReason.LIMIT_EXCEEDED,
        ),
        (
            AuthorizationDecision.DECLINE_EXPIRED,
            DeclineReason.EXPIRED_PAYMENT_METHOD,
        ),
        (
            AuthorizationDecision.DECLINE_VERIFICATION,
            DeclineReason.VERIFICATION_FAILED,
        ),
        (
            AuthorizationDecision.DECLINE_INVALID,
            DeclineReason.INVALID_PAYMENT_METHOD,
        ),
        (AuthorizationDecision.DECLINE_UNKNOWN, DeclineReason.UNKNOWN),
    ],
)
def test_declined_authorization_maps_reason_without_authorized_amount(
    decision: AuthorizationDecision,
    reason: DeclineReason,
) -> None:
    result = authorize(2500, decision)

    assert result.status is PaymentStatus.DECLINED
    assert result.authorized_amount == 0
    assert result.decline_reason is reason


@pytest.mark.parametrize("amount", [0, -1, -10_000])
def test_non_positive_amount_is_rejected_without_a_result(amount: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        authorize(amount, AuthorizationDecision.APPROVE)


def test_awaiting_payment_uses_the_existing_financial_invariants() -> None:
    state = PaymentState(
        status=PaymentStatus.AWAITING_PAYMENT,
        authorized_amount=0,
        captured_amount=0,
        refunded_amount=0,
    )

    assert state.authorized_amount == state.captured_amount == 0
    with pytest.raises(ValueError, match="Captured amount cannot exceed"):
        PaymentState(
            status=PaymentStatus.AWAITING_PAYMENT,
            authorized_amount=0,
            captured_amount=1,
            refunded_amount=0,
        )
