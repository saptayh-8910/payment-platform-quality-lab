"""Unit tests for webhook signatures and full-snapshot payload validation."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from payment_quality_lab.services.webhooks import (
    InvalidWebhookPayloadError,
    InvalidWebhookSignatureError,
    WebhookEventType,
    parse_webhook_payload,
    sign_webhook,
    verify_webhook_signature,
)

NOW = datetime(2026, 8, 18, 4, 0, tzinfo=UTC)
SECRET = "whsec_synthetic_test_only"


def event_payload() -> dict[str, object]:
    return {
        "aggregate_version": 2,
        "created_at": "2026-08-18T04:00:00Z",
        "id": "evt_test_capture",
        "payment": {
            "amount": 2500,
            "authorized_amount": 2500,
            "captured_amount": 2500,
            "created_at": "2026-08-18T03:59:00Z",
            "currency": "JPY",
            "id": "pay_test_webhook",
            "merchant_reference": "order-webhook-001",
            "refunded_amount": 0,
            "status": "CAPTURED",
            "updated_at": "2026-08-18T04:00:00Z",
            "version": 2,
        },
        "type": "payment.captured",
    }


def encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def signature(payload: bytes, timestamp: int | None = None) -> str:
    return sign_webhook(
        payload,
        secret=SECRET,
        timestamp=timestamp or int(NOW.timestamp()),
    )


def test_valid_signature_and_payload_are_accepted() -> None:
    payload = encode(event_payload())

    verify_webhook_signature(
        payload,
        signature_header=signature(payload),
        secret=SECRET,
        now=NOW,
    )
    envelope = parse_webhook_payload(payload)

    assert envelope.id == "evt_test_capture"
    assert envelope.event_type is WebhookEventType.CAPTURED
    assert envelope.aggregate_version == 2
    assert envelope.payment.status == "CAPTURED"
    assert envelope.payment.captured_amount == 2500


@pytest.mark.parametrize(
    ("payload_change", "secret"),
    [
        ("tamper", SECRET),
        ("original", "whsec_wrong_secret"),
    ],
)
def test_tampered_body_or_wrong_secret_is_rejected(
    payload_change: str,
    secret: str,
) -> None:
    original = encode(event_payload())
    supplied_signature = signature(original)
    checked = original.replace(b'"captured_amount":2500', b'"captured_amount":2499')
    if payload_change == "original":
        checked = original

    with pytest.raises(
        InvalidWebhookSignatureError,
        match="does not match",
    ):
        verify_webhook_signature(
            checked,
            signature_header=supplied_signature,
            secret=secret,
            now=NOW,
        )


@pytest.mark.parametrize(
    "header",
    [
        "",
        "v1=abc",
        "t=not-a-number,v1=abc",
        "t=1787025600",
        "t=1787025600,v1=short",
    ],
)
def test_missing_or_malformed_signature_is_rejected(header: str) -> None:
    with pytest.raises(InvalidWebhookSignatureError, match="Malformed"):
        verify_webhook_signature(
            encode(event_payload()),
            signature_header=header,
            secret=SECRET,
            now=NOW,
        )


@pytest.mark.parametrize("difference", [-301, 301])
def test_signature_timestamp_outside_tolerance_is_rejected(difference: int) -> None:
    payload = encode(event_payload())
    timestamp = int((NOW + timedelta(seconds=difference)).timestamp())

    with pytest.raises(InvalidWebhookSignatureError, match="outside tolerance"):
        verify_webhook_signature(
            payload,
            signature_header=signature(payload, timestamp),
            secret=SECRET,
            now=NOW,
        )


def test_empty_signing_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        sign_webhook(b"{}", secret="", timestamp=int(NOW.timestamp()))


@pytest.mark.parametrize(
    ("change", "expected_message"),
    [
        ("unknown_type", "event type is unsupported"),
        ("version_mismatch", "version does not match"),
        ("invalid_currency", "snapshot is invalid"),
        ("negative_amount", "amounts are inconsistent"),
        ("boolean_amount", "amount must be an integer"),
        ("missing_id", "id must be a non-empty string"),
        ("invalid_time", "created_at must be an ISO 8601 time"),
    ],
)
def test_invalid_payment_event_payload_is_rejected(
    change: str,
    expected_message: str,
) -> None:
    payload = deepcopy(event_payload())
    payment = payload["payment"]
    assert isinstance(payment, dict)
    if change == "unknown_type":
        payload["type"] = "payment.unknown"
    elif change == "version_mismatch":
        payment["version"] = 1
    elif change == "invalid_currency":
        payment["currency"] = "EUR"
    elif change == "negative_amount":
        payment["amount"] = -1
    elif change == "boolean_amount":
        payment["amount"] = True
    elif change == "missing_id":
        payload.pop("id")
    else:
        payload["created_at"] = "not-a-time"

    with pytest.raises(InvalidWebhookPayloadError, match=expected_message):
        parse_webhook_payload(encode(payload))


@pytest.mark.parametrize("payload", [b"not-json", b"\xff", b"[]"])
def test_non_object_or_invalid_json_body_is_rejected(payload: bytes) -> None:
    with pytest.raises(InvalidWebhookPayloadError):
        parse_webhook_payload(payload)
