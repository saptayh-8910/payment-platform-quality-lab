"""Unit and property-based tests for payment lifecycle invariants."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from payment_quality_lab.domain.payment import (
    InvalidPaymentTransitionError,
    PaymentOperation,
    PaymentState,
    PaymentStatus,
    RefundAmountExceededError,
    cancel,
    capture,
    refund,
)


def state(
    status: PaymentStatus,
    *,
    authorized: int = 1000,
    captured: int = 0,
    refunded: int = 0,
) -> PaymentState:
    return PaymentState(
        status=status,
        authorized_amount=authorized,
        captured_amount=captured,
        refunded_amount=refunded,
    )


def test_capture_reserves_the_full_authorized_amount() -> None:
    result = capture(state(PaymentStatus.AUTHORIZED))

    assert result == state(
        PaymentStatus.CAPTURED,
        captured=1000,
    )


@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.DECLINED,
        PaymentStatus.CAPTURED,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
        PaymentStatus.CANCELLED,
    ],
)
def test_capture_rejects_every_non_authorized_state(status: PaymentStatus) -> None:
    captured = (
        1000
        if status
        in {
            PaymentStatus.CAPTURED,
            PaymentStatus.PARTIALLY_REFUNDED,
            PaymentStatus.REFUNDED,
        }
        else 0
    )
    refunded = {
        PaymentStatus.PARTIALLY_REFUNDED: 400,
        PaymentStatus.REFUNDED: 1000,
    }.get(status, 0)

    with pytest.raises(InvalidPaymentTransitionError) as error:
        capture(state(status, captured=captured, refunded=refunded))

    assert error.value.operation is PaymentOperation.CAPTURE
    assert error.value.status is status


def test_cancel_preserves_authorized_balance_without_capture() -> None:
    result = cancel(state(PaymentStatus.AUTHORIZED))

    assert result == state(PaymentStatus.CANCELLED)


def test_cancel_awaiting_preserves_zero_balances() -> None:
    assert cancel(state(PaymentStatus.AWAITING_PAYMENT, authorized=0)) == state(
        PaymentStatus.CANCELLED, authorized=0
    )


@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.DECLINED,
        PaymentStatus.CAPTURED,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
        PaymentStatus.CANCELLED,
    ],
)
def test_cancel_rejects_disallowed_states(status: PaymentStatus) -> None:
    captured = (
        1000
        if status
        in {
            PaymentStatus.CAPTURED,
            PaymentStatus.PARTIALLY_REFUNDED,
            PaymentStatus.REFUNDED,
        }
        else 0
    )
    refunded = {
        PaymentStatus.PARTIALLY_REFUNDED: 400,
        PaymentStatus.REFUNDED: 1000,
    }.get(status, 0)

    with pytest.raises(InvalidPaymentTransitionError) as error:
        cancel(state(status, captured=captured, refunded=refunded))

    assert error.value.operation is PaymentOperation.CANCEL
    assert error.value.status is status


def test_partial_refund_preserves_captured_amount() -> None:
    result = refund(state(PaymentStatus.CAPTURED, captured=1000), 400)

    assert result == state(
        PaymentStatus.PARTIALLY_REFUNDED,
        captured=1000,
        refunded=400,
    )
    assert result.refundable_amount == 600


def test_remaining_refund_completes_payment() -> None:
    partially_refunded = state(
        PaymentStatus.PARTIALLY_REFUNDED,
        captured=1000,
        refunded=400,
    )

    result = refund(partially_refunded, 600)

    assert result == state(
        PaymentStatus.REFUNDED,
        captured=1000,
        refunded=1000,
    )
    assert result.refundable_amount == 0


@pytest.mark.parametrize("amount", [0, -1, -1000])
def test_refund_amount_must_be_positive(amount: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        refund(state(PaymentStatus.CAPTURED, captured=1000), amount)


def test_refund_cannot_exceed_remaining_captured_balance() -> None:
    partially_refunded = state(
        PaymentStatus.PARTIALLY_REFUNDED,
        captured=1000,
        refunded=400,
    )

    with pytest.raises(RefundAmountExceededError) as error:
        refund(partially_refunded, 601)

    assert error.value.requested == 601
    assert error.value.available == 600


@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.AUTHORIZED,
        PaymentStatus.DECLINED,
        PaymentStatus.REFUNDED,
        PaymentStatus.CANCELLED,
    ],
)
def test_refund_rejects_non_refundable_states(status: PaymentStatus) -> None:
    captured = 1000 if status is PaymentStatus.REFUNDED else 0
    refunded = captured

    with pytest.raises(InvalidPaymentTransitionError) as error:
        refund(state(status, captured=captured, refunded=refunded), 1)

    assert error.value.operation is PaymentOperation.REFUND


@pytest.mark.parametrize(
    ("authorized", "captured", "refunded", "message"),
    [
        (-1, 0, 0, "cannot be negative"),
        (1000, -1, 0, "cannot be negative"),
        (1000, 0, -1, "cannot be negative"),
        (1000, 1001, 0, "cannot exceed authorized"),
        (1000, 1000, 1001, "cannot exceed captured"),
    ],
)
def test_inconsistent_financial_state_is_rejected(
    authorized: int,
    captured: int,
    refunded: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        state(
            PaymentStatus.CAPTURED,
            authorized=authorized,
            captured=captured,
            refunded=refunded,
        )


@given(
    authorized=st.integers(min_value=1, max_value=999_999_999),
    refund_seed=st.integers(min_value=0, max_value=999_999_999),
)
def test_generated_refunds_never_exceed_capture(
    authorized: int,
    refund_seed: int,
) -> None:
    captured_state = capture(state(PaymentStatus.AUTHORIZED, authorized=authorized))
    refund_amount = (refund_seed % authorized) + 1

    result = refund(captured_state, refund_amount)

    assert result.captured_amount == authorized
    assert 0 < result.refunded_amount <= result.captured_amount
    assert result.refundable_amount + result.refunded_amount == authorized


@given(
    authorized=st.integers(min_value=2, max_value=999_999_999),
    split_seed=st.integers(min_value=0, max_value=999_999_999),
)
def test_generated_split_refunds_conserve_captured_total(
    authorized: int,
    split_seed: int,
) -> None:
    captured_state = capture(state(PaymentStatus.AUTHORIZED, authorized=authorized))
    first_amount = (split_seed % (authorized - 1)) + 1

    partial = refund(captured_state, first_amount)
    completed = refund(partial, partial.refundable_amount)

    assert partial.status is PaymentStatus.PARTIALLY_REFUNDED
    assert completed.status is PaymentStatus.REFUNDED
    assert completed.refunded_amount == completed.captured_amount == authorized
    assert completed.refundable_amount == 0
