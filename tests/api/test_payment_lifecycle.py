"""API contract tests for capture, cancellation, and refunds."""

import pytest
from fastapi.testclient import TestClient


def authorize_payment(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str = "lifecycle-authorize-0001",
) -> dict[str, object]:
    response = client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()


def lifecycle_request(
    client: TestClient,
    payment_id: str,
    operation: str,
    *,
    key: str,
    amount: int | None = None,
):
    return client.post(
        f"/payments/{payment_id}/{operation}",
        json={"amount": amount} if amount is not None else None,
        headers={"Idempotency-Key": key},
    )


def ledger(client: TestClient, payment_id: str) -> list[dict[str, object]]:
    response = client.get(f"/payments/{payment_id}/ledger")
    assert response.status_code == 200
    return response.json()


def test_capture_full_authorization_and_record_ledger_effect(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)

    response = lifecycle_request(
        client,
        created["id"],
        "capture",
        key="lifecycle-capture-0001",
    )

    assert response.status_code == 200
    captured = response.json()
    assert captured["status"] == "CAPTURED"
    assert captured["authorized_amount"] == 2500
    assert captured["captured_amount"] == 2500
    assert captured["refunded_amount"] == 0
    assert captured["version"] == 2
    assert [entry["operation"] for entry in ledger(client, created["id"])] == [
        "AUTHORIZATION",
        "CAPTURE",
    ]


def test_cancel_authorization_and_prevent_capture(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)

    cancelled_response = lifecycle_request(
        client,
        created["id"],
        "cancel",
        key="lifecycle-cancel-0001",
    )
    capture_response = lifecycle_request(
        client,
        created["id"],
        "capture",
        key="lifecycle-capture-after-cancel-0001",
    )

    assert cancelled_response.status_code == 200
    assert cancelled_response.json()["status"] == "CANCELLED"
    assert cancelled_response.json()["version"] == 2
    assert capture_response.status_code == 409
    assert capture_response.json() == {
        "code": "invalid_payment_transition",
        "message": "Cannot CAPTURE payment in CANCELLED state",
    }
    entries = ledger(client, created["id"])
    assert [(entry["operation"], entry["amount"]) for entry in entries] == [
        ("AUTHORIZATION", 2500),
        ("CANCEL", 2500),
    ]


def test_partial_then_remaining_refund_completes_payment(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    lifecycle_request(
        client,
        created["id"],
        "capture",
        key="lifecycle-capture-0002",
    )

    partial_response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="lifecycle-refund-0001",
        amount=1000,
    )
    remaining_response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="lifecycle-refund-0002",
        amount=1500,
    )

    partial = partial_response.json()
    assert partial_response.status_code == 200
    assert partial["status"] == "PARTIALLY_REFUNDED"
    assert partial["captured_amount"] == 2500
    assert partial["refunded_amount"] == 1000
    assert partial["version"] == 3

    refunded = remaining_response.json()
    assert remaining_response.status_code == 200
    assert refunded["status"] == "REFUNDED"
    assert refunded["refunded_amount"] == 2500
    assert refunded["version"] == 4

    entries = ledger(client, created["id"])
    assert [(entry["operation"], entry["amount"]) for entry in entries] == [
        ("AUTHORIZATION", 2500),
        ("CAPTURE", 2500),
        ("REFUND", 1000),
        ("REFUND", 1500),
    ]


def test_full_refund_in_one_operation(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    lifecycle_request(
        client,
        created["id"],
        "capture",
        key="lifecycle-capture-0003",
    )

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="lifecycle-refund-full-0001",
        amount=2500,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REFUNDED"
    assert response.json()["refunded_amount"] == 2500


@pytest.mark.parametrize("operation", ["capture", "cancel"])
def test_declined_payment_rejects_capture_and_cancellation(
    client: TestClient,
    approved_payload: dict[str, object],
    operation: str,
) -> None:
    approved_payload["payment_method_token"] = "tok_declined"
    declined = authorize_payment(client, approved_payload)

    response = lifecycle_request(
        client,
        declined["id"],
        operation,
        key=f"declined-{operation}-0001",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_payment_transition"
    assert client.get(f"/payments/{declined['id']}").json() == declined
    assert ledger(client, declined["id"]) == []


def test_authorized_payment_cannot_be_refunded_before_capture(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="refund-before-capture-0001",
        amount=1,
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "invalid_payment_transition",
        "message": "Cannot REFUND payment in AUTHORIZED state",
    }
    assert client.get(f"/payments/{created['id']}").json() == created


@pytest.mark.parametrize("operation", ["capture", "cancel"])
def test_captured_payment_rejects_second_capture_or_cancellation(
    client: TestClient,
    approved_payload: dict[str, object],
    operation: str,
) -> None:
    created = authorize_payment(client, approved_payload)
    captured = lifecycle_request(
        client,
        created["id"],
        "capture",
        key="capture-once-0001",
    ).json()

    response = lifecycle_request(
        client,
        created["id"],
        operation,
        key=f"captured-{operation}-0001",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_payment_transition"
    assert client.get(f"/payments/{created['id']}").json() == captured
    assert len(ledger(client, created["id"])) == 2


def test_over_refund_is_rejected_without_partial_state_change(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    captured = lifecycle_request(
        client,
        created["id"],
        "capture",
        key="capture-over-refund-0001",
    ).json()
    entries_before = ledger(client, created["id"])

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="over-refund-0001",
        amount=2501,
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "refund_amount_exceeded",
        "message": "Refund amount 2501 exceeds refundable amount 2500",
        "requested_amount": 2501,
        "refundable_amount": 2500,
    }
    assert client.get(f"/payments/{created['id']}").json() == captured
    assert ledger(client, created["id"]) == entries_before


def test_fully_refunded_payment_rejects_another_refund(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    lifecycle_request(
        client,
        created["id"],
        "capture",
        key="capture-refunded-0001",
    )
    refunded = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="refund-complete-0001",
        amount=2500,
    ).json()

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="refund-after-complete-0001",
        amount=1,
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Cannot REFUND payment in REFUNDED state"
    assert client.get(f"/payments/{created['id']}").json() == refunded


@pytest.mark.parametrize(
    ("operation", "amount"),
    [("capture", None), ("cancel", None), ("refund", 100)],
)
def test_lifecycle_operation_is_idempotent(
    client: TestClient,
    approved_payload: dict[str, object],
    operation: str,
    amount: int | None,
) -> None:
    created = authorize_payment(client, approved_payload)
    if operation == "refund":
        lifecycle_request(
            client,
            created["id"],
            "capture",
            key="capture-for-replay-0001",
        )
    key = f"replay-{operation}-0001"

    first = lifecycle_request(
        client,
        created["id"],
        operation,
        key=key,
        amount=amount,
    )
    replay = lifecycle_request(
        client,
        created["id"],
        operation,
        key=key,
        amount=amount,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    expected_entries = 3 if operation == "refund" else 2
    assert len(ledger(client, created["id"])) == expected_entries


def test_refund_key_reuse_with_different_amount_is_rejected(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    lifecycle_request(
        client,
        created["id"],
        "capture",
        key="capture-refund-conflict-0001",
    )
    lifecycle_request(
        client,
        created["id"],
        "refund",
        key="refund-conflict-0001",
        amount=100,
    )

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="refund-conflict-0001",
        amount=101,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"
    current = client.get(f"/payments/{created['id']}").json()
    assert current["refunded_amount"] == 100
    assert current["version"] == 3
    assert len(ledger(client, created["id"])) == 3


def test_key_reuse_across_different_operations_is_rejected(
    client: TestClient, approved_payload: dict[str, object]
) -> None:
    created = authorize_payment(client, approved_payload)
    shared_key = "cross-operation-conflict-0001"
    lifecycle_request(
        client,
        created["id"],
        "capture",
        key=shared_key,
    )

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key=shared_key,
        amount=100,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"
    assert len(ledger(client, created["id"])) == 2


@pytest.mark.parametrize("amount", [0, -1, 1_000_000_000])
def test_invalid_refund_amount_is_rejected_at_contract_boundary(
    client: TestClient,
    approved_payload: dict[str, object],
    amount: int,
) -> None:
    created = authorize_payment(client, approved_payload)

    response = lifecycle_request(
        client,
        created["id"],
        "refund",
        key="invalid-refund-amount-0001",
        amount=amount,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("operation", ["capture", "cancel", "refund"])
def test_missing_idempotency_key_is_rejected_for_lifecycle_operations(
    client: TestClient,
    operation: str,
) -> None:
    response = client.post(
        f"/payments/pay_missing/{operation}",
        json={"amount": 1} if operation == "refund" else None,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("operation", ["capture", "cancel", "refund"])
def test_unknown_payment_is_rejected_for_lifecycle_operations(
    client: TestClient,
    operation: str,
) -> None:
    response = lifecycle_request(
        client,
        "pay_missing",
        operation,
        key=f"missing-{operation}-0001",
        amount=1 if operation == "refund" else None,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "payment_not_found"
