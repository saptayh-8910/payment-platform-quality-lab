"""Unit tests for pure payment authorization rules."""

import pytest

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    PaymentStatus,
    authorize,
)


def test_approved_authorization_reserves_the_full_amount() -> None:
    result = authorize(2500, AuthorizationDecision.APPROVE)

    assert result.status is PaymentStatus.AUTHORIZED
    assert result.authorized_amount == 2500


def test_declined_authorization_has_no_authorized_amount() -> None:
    result = authorize(2500, AuthorizationDecision.DECLINE)

    assert result.status is PaymentStatus.DECLINED
    assert result.authorized_amount == 0


@pytest.mark.parametrize("amount", [0, -1, -10_000])
def test_non_positive_amount_is_rejected_without_a_result(amount: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        authorize(amount, AuthorizationDecision.APPROVE)
