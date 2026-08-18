"""Contract tests through the FastAPI boundary."""

import pytest
from fastapi.testclient import TestClient


def post_payment(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str = "idem-order-0001",
):
    return client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )


def test_health_endpoint_reports_ready_process(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_authorize_jpy_payment(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    response = post_payment(client, approved_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("pay_")
    assert body["merchant_reference"] == "order-2026-0001"
    assert body["amount"] == 2500
    assert body["currency"] == "JPY"
    assert body["status"] == "AUTHORIZED"
    assert body["authorized_amount"] == 2500
    assert body["captured_amount"] == 0
    assert body["refunded_amount"] == 0
    assert body["version"] == 1
    assert body["created_at"].endswith("Z")


def test_retrieve_created_payment(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = post_payment(client, approved_payload).json()

    response = client.get(f"/payments/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_authorization_creates_one_ledger_effect(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    payment = post_payment(client, approved_payload).json()

    response = client.get(f"/payments/{payment['id']}/ledger")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": response.json()[0]["id"],
            "payment_id": payment["id"],
            "operation": "AUTHORIZATION",
            "amount": 2500,
            "currency": "JPY",
            "created_at": payment["created_at"],
        }
    ]
    assert response.json()[0]["id"].startswith("led_")


def test_declined_payment_has_no_financial_ledger_effect(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    approved_payload["payment_method_token"] = "tok_declined"

    response = post_payment(client, approved_payload)

    assert response.status_code == 201
    payment = response.json()
    assert payment["status"] == "DECLINED"
    assert payment["authorized_amount"] == 0
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []


def test_equivalent_idempotent_retry_returns_original_payment(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    first = post_payment(client, approved_payload)
    replay = post_payment(client, approved_payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    payment_id = first.json()["id"]
    assert len(client.get(f"/payments/{payment_id}/ledger").json()) == 1


def test_idempotency_key_reuse_with_different_request_is_rejected(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    first = post_payment(client, approved_payload)
    approved_payload["amount"] = 2501

    conflict = post_payment(client, approved_payload)

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json() == {
        "code": "idempotency_conflict",
        "message": "Idempotency key was already used for another request",
    }


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("amount", 0),
        ("amount", -1),
        ("amount", 1_000_000_000),
        ("currency", "EUR"),
        ("payment_method_token", "real-card-token"),
        ("unexpected", "not allowed"),
    ],
)
def test_invalid_authorization_is_rejected(
    client: TestClient,
    approved_payload: dict[str, object],
    change: str,
    value: object,
) -> None:
    approved_payload[change] = value

    response = post_payment(client, approved_payload)

    assert response.status_code == 422


def test_missing_idempotency_key_is_rejected(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    response = client.post("/payments", json=approved_payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    ["/payments/pay_missing", "/payments/pay_missing/ledger"],
)
def test_unknown_payment_returns_consistent_error(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {
        "code": "payment_not_found",
        "message": "Payment pay_missing was not found",
    }


def test_openapi_exposes_payment_operations(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"/payments", "/payments/{payment_id}"}.issubset(paths)
