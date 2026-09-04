"""API contract evidence for asynchronous payment creation."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

FIXED_NOW = datetime(2026, 9, 4, 3, 15, tzinfo=UTC)


@pytest.fixture
def delayed_payload() -> dict[str, object]:
    return {
        "merchant_reference": "async-order-0001",
        "amount": 2500,
        "currency": "JPY",
        "payment_method_token": "tok_awaiting_confirmation",
    }


def post_payment(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str,
):
    return client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )


def test_conf_01_delayed_request_returns_deterministic_awaiting_payment(
    app: FastAPI,
    client: TestClient,
    delayed_payload: dict[str, object],
) -> None:
    app.state.payment_clock = lambda: FIXED_NOW

    response = post_payment(client, delayed_payload, key="async-create-key-0001")

    assert response.status_code == 201
    payment = response.json()
    assert payment["status"] == "AWAITING_PAYMENT"
    assert payment["payment_flow"] == "ASYNCHRONOUS_CONFIRMATION"
    assert payment["payment_reference"].startswith("ref_")
    assert len(payment["payment_reference"]) == 36
    assert datetime.fromisoformat(payment["created_at"]) == FIXED_NOW
    assert datetime.fromisoformat(payment["updated_at"]) == FIXED_NOW
    assert datetime.fromisoformat(payment["expires_at"]) == FIXED_NOW + timedelta(
        hours=72
    )
    assert payment["authorized_amount"] == 0
    assert payment["captured_amount"] == 0
    assert payment["refunded_amount"] == 0
    assert payment["decline_reason"] is None
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert client.get(f"/payments/{payment['id']}").json() == payment


def test_conf_01_separate_requests_receive_distinct_references(
    app: FastAPI,
    client: TestClient,
    delayed_payload: dict[str, object],
) -> None:
    app.state.payment_clock = lambda: FIXED_NOW
    first = post_payment(client, delayed_payload, key="async-unique-key-0001").json()
    delayed_payload["merchant_reference"] = "async-order-0002"
    second = post_payment(client, delayed_payload, key="async-unique-key-0002").json()

    assert first["id"] != second["id"]
    assert first["payment_reference"] != second["payment_reference"]


def test_conf_04_identical_replay_returns_the_complete_original_result(
    app: FastAPI,
    client: TestClient,
    delayed_payload: dict[str, object],
) -> None:
    app.state.payment_clock = lambda: FIXED_NOW
    first = post_payment(client, delayed_payload, key="async-replay-key-0001")
    app.state.payment_clock = lambda: FIXED_NOW + timedelta(days=1)

    replay = post_payment(client, delayed_payload, key="async-replay-key-0001")

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    payment = first.json()
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    events = client.get("/webhooks/events").json()
    assert len(events) == 1
    assert events[0]["type"] == "payment.confirmation_requested"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("merchant_reference", "async-order-changed"),
        ("amount", 2501),
        ("currency", "USD"),
        ("payment_method_token", "tok_approved"),
    ],
)
def test_conf_04_conflicting_reuse_changes_nothing(
    app: FastAPI,
    client: TestClient,
    delayed_payload: dict[str, object],
    field: str,
    replacement: object,
) -> None:
    app.state.payment_clock = lambda: FIXED_NOW
    first = post_payment(client, delayed_payload, key="async-conflict-key-0001")
    changed = dict(delayed_payload)
    changed[field] = replacement

    conflict = post_payment(client, changed, key="async-conflict-key-0001")

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    original = first.json()
    assert client.get(f"/payments/{original['id']}").json() == original
    assert client.get(f"/payments/{original['id']}/ledger").json() == []
    assert len(client.get("/webhooks/events").json()) == 1


def test_existing_synchronous_response_has_no_delayed_metadata(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    response = post_payment(client, approved_payload, key="sync-metadata-key-0001")

    assert response.status_code == 201
    payment = response.json()
    assert payment["payment_flow"] == "SYNCHRONOUS"
    assert payment["payment_reference"] is None
    assert payment["expires_at"] is None
