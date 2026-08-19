"""HTTP contract tests for webhook producer and consumer behavior."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payment_quality_lab.main import DEFAULT_WEBHOOK_SIGNING_SECRET, create_app
from payment_quality_lab.services.webhooks import sign_webhook


@pytest.fixture
def webhook_test_app(tmp_path) -> Iterator[FastAPI]:
    application = create_app(
        f"sqlite:///{tmp_path / 'webhook-api.db'}",
        enable_failure_injection=True,
    )
    yield application
    application.state.engine.dispose()


@pytest.fixture
def webhook_test_client(webhook_test_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(webhook_test_app) as test_client:
        yield test_client


def authorize(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str = "webhook-api-authorize",
) -> dict[str, object]:
    response = client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()


def event_body(event: dict[str, object]) -> bytes:
    payload = event["payload"]
    assert isinstance(payload, dict)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def signature(body: bytes) -> str:
    return sign_webhook(
        body,
        secret=DEFAULT_WEBHOOK_SIGNING_SECRET,
        timestamp=int(datetime.now(UTC).timestamp()),
    )


def test_payment_api_exposes_transactional_outbox_event(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    payment = authorize(client, approved_payload)

    response = client.get("/webhooks/events")

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    event = events[0]
    assert event["payment_id"] == payment["id"]
    assert event["type"] == "payment.authorized"
    assert event["aggregate_version"] == 1
    assert event["status"] == "PENDING"
    assert event["attempt_count"] == 0
    assert event["payload"]["payment"] == payment


def test_signed_consumer_request_applies_once_and_duplicate_is_safe(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    payment = authorize(client, approved_payload)
    event = client.get("/webhooks/events").json()[0]
    body = event_body(event)
    headers = {
        "Content-Type": "application/json",
        "Webhook-Signature": signature(body),
    }

    first = client.post("/webhook-consumer", content=body, headers=headers)
    duplicate = client.post("/webhook-consumer", content=body, headers=headers)
    projection = client.get(f"/merchant-projections/{payment['id']}")

    assert first.status_code == 200
    assert first.json()["disposition"] == "APPLIED"
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 200
    assert duplicate.json()["disposition"] == "DUPLICATE"
    assert duplicate.json()["duplicate"] is True
    assert projection.status_code == 200
    assert projection.json()["status"] == "AUTHORIZED"
    assert projection.json()["aggregate_version"] == 1


def test_invalid_signature_changes_no_consumer_state(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    payment = authorize(client, approved_payload)
    event = client.get("/webhooks/events").json()[0]
    body = event_body(event)

    response = client.post(
        "/webhook-consumer",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Webhook-Signature": "t=0,v1=" + ("0" * 64),
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_webhook_signature"
    projection = client.get(f"/merchant-projections/{payment['id']}")
    assert projection.status_code == 404


def test_signed_invalid_payload_returns_clear_contract_error(
    client: TestClient,
) -> None:
    body = b'{"id":"evt_invalid"}'

    response = client.post(
        "/webhook-consumer",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Webhook-Signature": signature(body),
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_webhook_payload"


def test_delivery_endpoint_updates_attempt_history_and_projection(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    payment = authorize(client, approved_payload)
    event = client.get("/webhooks/events").json()[0]

    delivery = client.post(f"/webhooks/events/{event['id']}/deliver")
    attempts = client.get(f"/webhooks/events/{event['id']}/attempts")
    projection = client.get(f"/merchant-projections/{payment['id']}")

    assert delivery.status_code == 200
    assert delivery.json()["status"] == "DELIVERED"
    assert delivery.json()["outcome"] == "SUCCESS"
    assert attempts.status_code == 200
    assert attempts.json() == [
        {
            "attempt_number": 1,
            "outcome": "SUCCESS",
            "response_status": 200,
            "error_code": None,
            "attempted_at": attempts.json()[0]["attempted_at"],
        }
    ]
    assert projection.json()["payment_id"] == payment["id"]

    repeated_delivery = client.post(f"/webhooks/events/{event['id']}/deliver")
    assert repeated_delivery.status_code == 409
    assert repeated_delivery.json()["code"] == "webhook_delivery_not_ready"


def test_delivery_failure_control_is_disabled_by_default(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    authorize(client, approved_payload)
    event = client.get("/webhooks/events").json()[0]

    response = client.post(
        f"/webhooks/events/{event['id']}/deliver",
        headers={"X-Payment-Lab-Delivery-Failure": "before_delivery"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "failure_injection_disabled"
    assert client.get(f"/webhooks/events/{event['id']}/attempts").json() == []


def test_consumer_failure_control_is_disabled_by_default(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    authorize(client, approved_payload)
    event = client.get("/webhooks/events").json()[0]
    body = event_body(event)

    response = client.post(
        "/webhook-consumer",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Webhook-Signature": signature(body),
            "X-Payment-Lab-Consumer-Failure": "after_inbox",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "failure_injection_disabled"


def test_enabled_consumer_failure_rolls_back_and_retry_succeeds(
    webhook_test_client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = authorize(webhook_test_client, approved_payload)
    event = webhook_test_client.get("/webhooks/events").json()[0]
    body = event_body(event)
    headers = {
        "Content-Type": "application/json",
        "Webhook-Signature": signature(body),
        "X-Payment-Lab-Consumer-Failure": "after_inbox",
    }

    failure = webhook_test_client.post(
        "/webhook-consumer",
        content=body,
        headers=headers,
    )
    headers.pop("X-Payment-Lab-Consumer-Failure")
    retry = webhook_test_client.post(
        "/webhook-consumer",
        content=body,
        headers=headers,
    )

    assert failure.status_code == 503
    assert failure.json()["code"] == "simulated_consumer_failure"
    assert retry.status_code == 200
    assert retry.json()["disposition"] == "APPLIED"
    assert (
        webhook_test_client.get(f"/merchant-projections/{payment['id']}").status_code
        == 200
    )


@pytest.mark.parametrize(
    "path",
    [
        "/webhooks/events/evt_missing/attempts",
        "/merchant-projections/pay_missing",
    ],
)
def test_unknown_webhook_resources_return_not_found(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 404


def test_openapi_exposes_webhook_operations(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert {
        "/webhooks/events",
        "/webhooks/events/{event_id}/attempts",
        "/webhooks/events/{event_id}/deliver",
        "/webhook-consumer",
        "/merchant-projections/{payment_id}",
    }.issubset(paths)
