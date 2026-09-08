"""Focused unit evidence for the confirmation trust boundary."""

from datetime import UTC, datetime, timedelta

import pytest

from payment_quality_lab.services.confirmations import (
    InvalidConfirmationSignatureError,
    read_confirmation_clock,
    verify_confirmation_signature,
)
from payment_quality_lab.services.webhooks import sign_webhook

NOW = datetime(2026, 9, 9, 1, 30, tzinfo=UTC)
SECRET = "cnfsec_unit_test"
BODY = b'{"confirmation_id":"cnf_unit"}'


def signature(at: datetime = NOW, *, secret: str = SECRET) -> str:
    return sign_webhook(BODY, secret=secret, timestamp=int(at.timestamp()))


def test_sec_c01_shared_hmac_format_authenticates_the_exact_body() -> None:
    verify_confirmation_signature(
        BODY,
        signature_header=signature(),
        secret=SECRET,
        received_at=NOW,
    )


@pytest.mark.parametrize(
    "supplied",
    [
        None,
        "",
        "malformed",
        signature(secret="wrong-secret"),
        signature(NOW - timedelta(minutes=6)),
        signature(NOW + timedelta(minutes=6)),
    ],
)
def test_sec_c02_untrusted_signatures_are_rejected(supplied: str | None) -> None:
    with pytest.raises(InvalidConfirmationSignatureError):
        verify_confirmation_signature(
            BODY,
            signature_header=supplied,
            secret=SECRET,
            received_at=NOW,
        )


def test_confirmation_clock_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        read_confirmation_clock(lambda: datetime(2026, 9, 9, 1, 30))
