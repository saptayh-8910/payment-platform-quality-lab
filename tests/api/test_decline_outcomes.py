"""API contracts for detailed, provider-neutral decline outcomes."""

import json

import pytest
from fastapi.testclient import TestClient

DECLINE_CASES = [
    ("tok_declined_insufficient_funds", "insufficient_funds"),
    ("tok_declined_limit_exceeded", "limit_exceeded"),
    ("tok_declined_expired", "expired_payment_method"),
    ("tok_declined_verification", "verification_failed"),
    ("tok_declined_invalid", "invalid_payment_method"),
    ("tok_declined_unknown", "unknown"),
]


def post_decline(
    client: TestClient,
    approved_payload: dict[str, object],
    *,
    token: str,
    key: str,
):
    payload = {**approved_payload, "payment_method_token": token}
    return client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )


@pytest.mark.parametrize(("token", "reason"), DECLINE_CASES)
def test_each_decline_returns_and_retrieves_its_normalized_reason(
    client: TestClient,
    approved_payload: dict[str, object],
    token: str,
    reason: str,
) -> None:
    response = post_decline(
        client,
        approved_payload,
        token=token,
        key=f"api-{reason}",
    )

    assert response.status_code == 201
    payment = response.json()
    assert payment["status"] == "DECLINED"
    assert payment["decline_reason"] == reason
    assert payment["authorized_amount"] == 0
    assert payment["captured_amount"] == 0
    assert payment["refunded_amount"] == 0
    assert client.get(f"/payments/{payment['id']}").json() == payment
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert token not in json.dumps(payment)


def test_legacy_decline_token_remains_a_safe_unknown_alias(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    response = post_decline(
        client,
        approved_payload,
        token="tok_declined",
        key="api-legacy-decline-alias",
    )

    assert response.status_code == 201
    assert response.json()["decline_reason"] == "unknown"


def test_authorized_payment_has_no_decline_reason(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    response = client.post(
        "/payments",
        json=approved_payload,
        headers={"Idempotency-Key": "api-approved-no-decline"},
    )

    assert response.status_code == 201
    assert response.json()["decline_reason"] is None


def test_identical_decline_replay_preserves_the_complete_original_result(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    first = post_decline(
        client,
        approved_payload,
        token="tok_declined_verification",
        key="api-decline-replay",
    )
    replay = post_decline(
        client,
        approved_payload,
        token="tok_declined_verification",
        key="api-decline-replay",
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    payment_id = first.json()["id"]
    matching_events = [
        event
        for event in client.get("/webhooks/events").json()
        if event["payment_id"] == payment_id
    ]
    assert len(matching_events) == 1
    assert client.get(f"/payments/{payment_id}/ledger").json() == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("payment_method_token", "tok_declined_limit_exceeded"),
        ("amount", 2501),
        ("currency", "USD"),
        ("merchant_reference", "changed-reference"),
    ],
)
def test_conflicting_decline_replay_changes_nothing(
    client: TestClient,
    approved_payload: dict[str, object],
    field: str,
    value: object,
) -> None:
    key = f"api-decline-conflict-{field}"
    original_payload = {
        **approved_payload,
        "payment_method_token": "tok_declined_insufficient_funds",
    }
    first = client.post(
        "/payments",
        json=original_payload,
        headers={"Idempotency-Key": key},
    )
    changed_payload = {**original_payload, field: value}

    conflict = client.post(
        "/payments",
        json=changed_payload,
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    original = first.json()
    assert client.get(f"/payments/{original['id']}").json() == original
    assert client.get(f"/payments/{original['id']}/ledger").json() == []
    events = client.get("/webhooks/events").json()
    assert [event["payment_id"] for event in events] == [original["id"]]
