"""HTTP contract tests for asynchronous payment confirmations."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from payment_quality_lab.domain.payment import Currency
from payment_quality_lab.main import DEFAULT_CONFIRMATION_SIGNING_SECRET
from payment_quality_lab.persistence.models import ConfirmationReceiptRecord
from payment_quality_lab.services import confirmations, payments
from payment_quality_lab.services.webhooks import sign_webhook

CREATED_AT = datetime(2026, 9, 9, 2, 0, tzinfo=UTC)
RECEIVED_AT = CREATED_AT + timedelta(hours=1)


@pytest.mark.parametrize("currency", ["JPY", "USD"])
def test_canc_a_b_c_d_cancel_replay_and_later_confirmation(app, client, currency):
    payment = create_delayed_payment(app, client, currency=currency)
    url = f"/payments/{payment['id']}/cancel"
    headers = {"Idempotency-Key": "awaiting-cancel-key"}
    response = client.post(url, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "CANCELLED"
    assert result["version"] == 2
    assert (
        result["authorized_amount"]
        == result["captured_amount"]
        == result["refunded_amount"]
        == 0
    )
    for field in ["payment_reference", "payment_flow", "expires_at", "created_at"]:
        assert result[field] == payment[field]
    assert client.post(url, headers=headers).json() == result
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert (
        client.post(url, headers={"Idempotency-Key": "fresh-cancel-key"}).status_code
        == 409
    )
    other = create_delayed_payment(app, client, key="another-delayed-payment")
    assert (
        client.post(f"/payments/{other['id']}/cancel", headers=headers).status_code
        == 409
    )
    assert (
        client.post(f"/payments/{payment['id']}/capture", headers=headers).status_code
        == 409
    )
    payload = confirmation_payload(payment["payment_reference"], currency=currency)
    confirmed = signed_confirmation(app, client, payload)
    assert confirmed.status_code == 200
    diagnostic = client.get(
        f"/internal/payment-confirmations/{payload['confirmation_id']}"
    )
    assert diagnostic.status_code == 200
    assert diagnostic.json()["disposition"] == "already_resolved"
    assert client.get(f"/payments/{payment['id']}").json() == result


def test_canc_f_pending_api_conflict(app, client):
    payment = create_delayed_payment(app, client)
    with app.state.session_factory() as session:
        confirmations.accept_confirmation(
            session,
            command=confirmations.ConfirmationCommand(
                "cnf_pending_cancel", payment["payment_reference"], 2500, Currency.JPY
            ),
            clock=lambda: RECEIVED_AT,
        )
    response = client.post(
        f"/payments/{payment['id']}/cancel",
        headers={"Idempotency-Key": "pending-cancel-key"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "code": "confirmation_pending",
        "message": (
            "A payment confirmation is pending. "
            "Check the payment status before cancelling."
        ),
    }


def test_canc_p_api_database_failure_is_safe(app, client, monkeypatch):
    payment = create_delayed_payment(app, client)
    with monkeypatch.context() as patch:

        def fail(session):
            raise OperationalError("private database details", {}, Exception("secret"))

        patch.setattr(payments, "begin_coordinated_write", fail)
        response = client.post(
            f"/payments/{payment['id']}/cancel",
            headers={"Idempotency-Key": "unavailable-cancel-key"},
        )
    assert response.status_code == 503
    assert response.json() == {
        "code": "cancellation_unavailable",
        "message": "Retry cancellation with the same idempotency key",
    }
    assert (
        client.post(
            f"/payments/{payment['id']}/cancel",
            headers={"Idempotency-Key": "unavailable-cancel-key"},
        ).status_code
        == 200
    )


def create_delayed_payment(
    app: FastAPI,
    client: TestClient,
    *,
    amount: int = 2500,
    currency: str = "JPY",
    key: str = "confirmation-create-key",
) -> dict[str, Any]:
    app.state.payment_clock = lambda: CREATED_AT
    response = client.post(
        "/payments",
        headers={"Idempotency-Key": key},
        json={
            "merchant_reference": f"order-{key}",
            "amount": amount,
            "currency": currency,
            "payment_method_token": "tok_awaiting_confirmation",
        },
    )
    assert response.status_code == 201
    return response.json()


def confirmation_payload(
    payment_reference: str,
    *,
    confirmation_id: str = "cnf_confirmation_0001",
    amount: int = 2500,
    currency: str = "JPY",
) -> dict[str, object]:
    return {
        "confirmation_id": confirmation_id,
        "payment_reference": payment_reference,
        "amount": amount,
        "currency": currency,
    }


def signed_confirmation(
    app: FastAPI,
    client: TestClient,
    payload: dict[str, object],
    *,
    received_at: datetime = RECEIVED_AT,
):
    app.state.confirmation_clock = lambda: received_at
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = sign_webhook(
        body,
        secret=DEFAULT_CONFIRMATION_SIGNING_SECRET,
        timestamp=int(received_at.timestamp()),
    )
    return client.post(
        "/payment-confirmations",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Confirmation-Signature": signature,
        },
    )


def test_sec_c01_and_conf_02_matching_confirmation_is_safely_acknowledged(
    app: FastAPI,
    client: TestClient,
) -> None:
    payment = create_delayed_payment(app, client)
    payload = confirmation_payload(payment["payment_reference"])

    response = signed_confirmation(app, client, payload)

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert "disposition" not in response.text
    captured = client.get(f"/payments/{payment['id']}").json()
    assert captured["status"] == "CAPTURED"
    assert captured["authorized_amount"] == 2500
    assert captured["captured_amount"] == 2500
    assert captured["version"] == 2
    ledger = client.get(f"/payments/{payment['id']}/ledger").json()
    assert [(entry["operation"], entry["amount"]) for entry in ledger] == [
        ("CONFIRMATION_CAPTURE", 2500)
    ]
    events = client.get("/webhooks/events").json()
    assert [event["type"] for event in events] == [
        "payment.confirmation_requested",
        "payment.captured",
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Confirmation-Signature": "malformed"},
        {"Confirmation-Signature": "t=0,v1=" + ("0" * 64)},
    ],
)
def test_sec_c02_invalid_signature_has_zero_side_effects(
    app: FastAPI,
    client: TestClient,
    headers: dict[str, str],
) -> None:
    payment = create_delayed_payment(app, client)
    app.state.confirmation_clock = lambda: RECEIVED_AT
    payload = confirmation_payload(payment["payment_reference"])
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    response = client.post(
        "/payment-confirmations",
        content=body,
        headers={"Content-Type": "application/json", **headers},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_confirmation_signature"
    assert client.get(f"/payments/{payment['id']}").json() == payment
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert len(client.get("/webhooks/events").json()) == 1
    diagnostic = client.get("/internal/payment-confirmations/cnf_confirmation_0001")
    assert diagnostic.status_code == 404
    with app.state.session_factory() as session:
        assert list(session.scalars(select(ConfirmationReceiptRecord))) == []


def test_authenticated_malformed_payload_returns_safe_422(
    app: FastAPI,
    client: TestClient,
) -> None:
    payment = create_delayed_payment(app, client)
    app.state.confirmation_clock = lambda: RECEIVED_AT
    body = b'{"confirmation_id":"cnf_invalid","secret":"do-not-store"}'
    signature = sign_webhook(
        body,
        secret=DEFAULT_CONFIRMATION_SIGNING_SECRET,
        timestamp=int(RECEIVED_AT.timestamp()),
    )

    response = client.post(
        "/payment-confirmations",
        content=body,
        headers={"Confirmation-Signature": signature},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_confirmation_payload",
        "message": "Confirmation payload does not match the required contract",
    }
    assert client.get(f"/payments/{payment['id']}").json() == payment

    with app.state.session_factory() as session:
        assert list(session.scalars(select(ConfirmationReceiptRecord))) == []


def test_processing_failure_returns_safe_503_and_retry_completes_original_receipt(
    app, client, monkeypatch
):
    payment = create_delayed_payment(app, client)
    payload = confirmation_payload(payment["payment_reference"])
    original = confirmations.create_outbox_event

    def fail(*args, **kwargs):
        raise RuntimeError("private failure details")

    monkeypatch.setattr(confirmations, "create_outbox_event", fail)
    response = signed_confirmation(app, client, payload)
    assert response.status_code == 503
    assert response.json() == {
        "code": "confirmation_processing_unavailable",
        "message": "Retry with the same confirmation ID and payload",
    }
    receipt_url = "/internal/confirmation-receipts/cnf_confirmation_0001"
    receipt = client.get(receipt_url).json()
    assert receipt["completed"] is False
    assert client.get("/internal/confirmation-receipts/cnf_missing").status_code == 404
    assert client.get(f"/payments/{payment['id']}").json() == payment
    monkeypatch.setattr(confirmations, "create_outbox_event", original)
    retry = signed_confirmation(
        app, client, payload, received_at=CREATED_AT + timedelta(hours=80)
    )
    assert retry.status_code == 200 and retry.headers["Idempotent-Replayed"] == "true"
    assert client.get(receipt_url).json() == {**receipt, "completed": True}
    assert len(client.get(f"/payments/{payment['id']}/ledger").json()) == 1


def test_dup_01_identical_replay_returns_original_safe_result_once(
    app: FastAPI,
    client: TestClient,
) -> None:
    payment = create_delayed_payment(app, client)
    payload = confirmation_payload(payment["payment_reference"])
    first = signed_confirmation(app, client, payload)
    app.state.confirmation_clock = lambda: RECEIVED_AT + timedelta(minutes=1)

    replay = signed_confirmation(
        app,
        client,
        payload,
        received_at=RECEIVED_AT + timedelta(minutes=1),
    )

    assert replay.status_code == 200
    assert replay.json() == first.json() == {"accepted": True}
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert len(client.get(f"/payments/{payment['id']}/ledger").json()) == 1
    assert len(client.get("/webhooks/events").json()) == 2


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("payment_reference", "ref_" + ("f" * 32)),
        ("amount", 2501),
        ("currency", "USD"),
    ],
)
def test_dup_02_changed_payload_with_same_confirmation_id_conflicts(
    app: FastAPI,
    client: TestClient,
    field: str,
    replacement: object,
) -> None:
    payment = create_delayed_payment(app, client)
    original = confirmation_payload(payment["payment_reference"])
    assert signed_confirmation(app, client, original).status_code == 200
    changed = dict(original)
    changed[field] = replacement

    conflict = signed_confirmation(app, client, changed)

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "confirmation_id_conflict"
    assert len(client.get(f"/payments/{payment['id']}/ledger").json()) == 1
    assert len(client.get("/webhooks/events").json()) == 2


@pytest.mark.parametrize(
    ("changes", "expected_disposition"),
    [
        ({"amount": 2501}, "amount_mismatch"),
        ({"currency": "USD"}, "currency_mismatch"),
        ({"payment_reference": "ref_" + ("f" * 32)}, "unknown_reference"),
    ],
)
def test_anomalies_share_safe_response_but_remain_diagnosable(
    app: FastAPI,
    client: TestClient,
    changes: dict[str, object],
    expected_disposition: str,
) -> None:
    payment = create_delayed_payment(app, client)
    payload = confirmation_payload(payment["payment_reference"])
    payload.update(changes)

    response = signed_confirmation(app, client, payload)

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert expected_disposition not in response.text
    diagnostic = client.get("/internal/payment-confirmations/cnf_confirmation_0001")
    assert diagnostic.status_code == 200
    assert diagnostic.json()["disposition"] == expected_disposition
    assert client.get(f"/payments/{payment['id']}").json() == payment
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert len(client.get("/webhooks/events").json()) == 1


def test_cap_01_new_confirmation_for_captured_payment_has_no_second_effect(
    app: FastAPI,
    client: TestClient,
) -> None:
    payment = create_delayed_payment(app, client)
    first = confirmation_payload(payment["payment_reference"])
    assert signed_confirmation(app, client, first).status_code == 200
    second = confirmation_payload(
        payment["payment_reference"],
        confirmation_id="cnf_confirmation_0002",
    )

    response = signed_confirmation(app, client, second)

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    diagnostic = client.get(
        "/internal/payment-confirmations/cnf_confirmation_0002"
    ).json()
    assert diagnostic["disposition"] == "already_resolved"
    assert len(client.get(f"/payments/{payment['id']}/ledger").json()) == 1
    assert len(client.get("/webhooks/events").json()) == 2


def test_late_02_boundary_confirmation_expires_without_financial_effect(
    app: FastAPI,
    client: TestClient,
) -> None:
    payment = create_delayed_payment(app, client)
    payload = confirmation_payload(payment["payment_reference"])
    boundary = CREATED_AT + timedelta(hours=72)

    response = signed_confirmation(app, client, payload, received_at=boundary)

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    expired = client.get(f"/payments/{payment['id']}").json()
    assert expired["status"] == "EXPIRED"
    assert expired["authorized_amount"] == expired["captured_amount"] == 0
    assert client.get(f"/payments/{payment['id']}/ledger").json() == []
    assert [event["type"] for event in client.get("/webhooks/events").json()] == [
        "payment.confirmation_requested",
        "payment.expired",
    ]
    diagnostic = client.get(
        "/internal/payment-confirmations/cnf_confirmation_0001"
    ).json()
    assert diagnostic["disposition"] == "late"
