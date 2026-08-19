"""HTTP contracts for settlement import and reconciliation reports."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def create_captured_payment(
    client: TestClient,
    approved_payload: dict[str, object],
    *,
    suffix: str,
    amount: int = 2500,
    currency: str = "JPY",
) -> dict[str, object]:
    payload = {
        **approved_payload,
        "merchant_reference": f"reconciliation-{suffix}",
        "amount": amount,
        "currency": currency,
    }
    authorization = client.post(
        "/payments",
        json=payload,
        headers={"Idempotency-Key": f"reconciliation-authorize-{suffix}"},
    )
    assert authorization.status_code == 201
    payment = authorization.json()
    capture = client.post(
        f"/payments/{payment['id']}/capture",
        headers={"Idempotency-Key": f"reconciliation-capture-{suffix}"},
    )
    assert capture.status_code == 200
    return capture.json()


def deliver_payment_events(client: TestClient, payment_id: str) -> None:
    events = [
        event
        for event in client.get("/webhooks/events").json()
        if event["payment_id"] == payment_id
    ]
    for event in sorted(events, key=lambda value: value["aggregate_version"]):
        response = client.post(f"/webhooks/events/{event['id']}/deliver")
        assert response.status_code == 200


def import_batch(
    client: TestClient,
    entries: list[dict[str, object]],
) -> dict[str, object]:
    response = client.post(
        "/settlement-batches",
        json={
            "cutoff": (datetime.now(UTC) + timedelta(seconds=5)).isoformat(),
            "entries": entries,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_clean_reconciliation_report_is_communicative_and_sanitized(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = create_captured_payment(
        client,
        approved_payload,
        suffix="clean",
    )
    deliver_payment_events(client, str(payment["id"]))
    batch = import_batch(
        client,
        [
            {
                "payment_id": payment["id"],
                "amount": 2500,
                "currency": "JPY",
            }
        ],
    )

    response = client.post(
        "/reconciliation-reports",
        json={"settlement_batch_id": batch["id"]},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["currency_totals"] == [
        {
            "currency": "JPY",
            "expected_settlement_total": 2500,
            "observed_settlement_total": 2500,
            "net_discrepancy": 0,
        }
    ]
    assert report["items"][0]["ledger_status"] == "matched"
    assert report["items"][0]["projection_status"] == "matched"
    serialized = json.dumps(report)
    assert "payment_method_token" not in serialized
    assert "whsec" not in serialized
    assert "Webhook-Signature" not in serialized


def test_mismatch_report_explains_expected_and_observed_values(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = create_captured_payment(
        client,
        approved_payload,
        suffix="mismatch",
    )
    deliver_payment_events(client, str(payment["id"]))
    batch = import_batch(
        client,
        [
            {
                "payment_id": payment["id"],
                "amount": 2400,
                "currency": "JPY",
            }
        ],
    )

    response = client.post(
        "/reconciliation-reports",
        json={"settlement_batch_id": batch["id"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["settlement_classification"] == "amount_mismatched"
    assert item["expected_settlement_amount"] == 2500
    assert item["observed_settlement_amounts"] == [2400]


def test_imported_batch_preserves_duplicate_source_line_numbers(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = create_captured_payment(
        client,
        approved_payload,
        suffix="duplicate-lines",
    )
    entries = [
        {"payment_id": payment["id"], "amount": 2500, "currency": "JPY"},
        {"payment_id": payment["id"], "amount": 2500, "currency": "JPY"},
    ]

    batch = import_batch(client, entries)
    retrieved = client.get(f"/settlement-batches/{batch['id']}")

    assert [entry["line_number"] for entry in batch["entries"]] == [1, 2]
    assert retrieved.status_code == 200
    assert retrieved.json() == batch


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/settlement-batches/setb_missing", None),
        (
            "post",
            "/reconciliation-reports",
            {"settlement_batch_id": "setb_missing"},
        ),
    ],
)
def test_unknown_settlement_batch_returns_not_found(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    response = client.request(method, path, json=payload)

    assert response.status_code == 404
    assert response.json()["code"] == "settlement_batch_not_found"


def test_unknown_payment_row_is_rejected(
    client: TestClient,
) -> None:
    response = client.post(
        "/settlement-batches",
        json={
            "cutoff": datetime.now(UTC).isoformat(),
            "entries": [
                {
                    "payment_id": "pay_missing",
                    "amount": 1000,
                    "currency": "JPY",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "settlement_payment_not_found"


def test_payment_created_after_batch_cutoff_is_rejected(
    client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = create_captured_payment(
        client,
        approved_payload,
        suffix="outside-cutoff",
    )

    response = client.post(
        "/settlement-batches",
        json={
            "cutoff": "2020-01-01T00:00:00Z",
            "entries": [
                {
                    "payment_id": payment["id"],
                    "amount": 2500,
                    "currency": "JPY",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "settlement_payment_outside_cutoff"


@pytest.mark.parametrize(
    "entry",
    [
        {"payment_id": "pay_test", "amount": 0, "currency": "JPY"},
        {"payment_id": "pay_test", "amount": 100, "currency": "EUR"},
        {
            "payment_id": "pay_test",
            "amount": 100,
            "currency": "JPY",
            "unexpected": True,
        },
    ],
)
def test_invalid_settlement_row_fails_schema_validation(
    client: TestClient,
    entry: dict[str, object],
) -> None:
    response = client.post(
        "/settlement-batches",
        json={"cutoff": datetime.now(UTC).isoformat(), "entries": [entry]},
    )

    assert response.status_code == 422


def test_settlement_cutoff_requires_an_explicit_timezone(client: TestClient) -> None:
    response = client.post(
        "/settlement-batches",
        json={"cutoff": "2026-08-19T05:00:00", "entries": []},
    )

    assert response.status_code == 422


def test_openapi_exposes_reconciliation_operations(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert {
        "/settlement-batches",
        "/settlement-batches/{batch_id}",
        "/reconciliation-reports",
    }.issubset(paths)
