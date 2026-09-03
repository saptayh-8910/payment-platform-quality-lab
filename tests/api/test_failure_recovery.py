"""API tests for deterministic timeout controls and safe client recovery."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from payment_quality_lab.main import create_app
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
)


@pytest.fixture
def reliability_app(tmp_path) -> Iterator[FastAPI]:
    application = create_app(
        f"sqlite:///{tmp_path / 'api-reliability.db'}",
        enable_failure_injection=True,
        initialize_schema=True,
    )
    yield application
    application.state.engine.dispose()


@pytest.fixture
def reliability_client(reliability_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(reliability_app) as test_client:
        yield test_client


def authorize(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str,
    failure: str | None = None,
):
    headers = {"Idempotency-Key": key}
    if failure is not None:
        headers["X-Payment-Lab-Failure"] = failure
    return client.post("/payments", json=payload, headers=headers)


def test_failure_control_is_rejected_when_not_explicitly_enabled(
    client: TestClient,
    app: FastAPI,
    approved_payload: dict[str, object],
) -> None:
    response = authorize(
        client,
        approved_payload,
        key="disabled-failure-control",
        failure="before_commit",
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "failure_injection_disabled",
        "message": "Test failure controls are disabled",
    }
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentRecord)) == 0


def test_pre_commit_timeout_leaves_no_effect_and_retry_is_fresh(
    reliability_client: TestClient,
    reliability_app: FastAPI,
    approved_payload: dict[str, object],
) -> None:
    key = "api-timeout-before-commit"
    timeout = authorize(
        reliability_client,
        approved_payload,
        key=key,
        failure="before_commit",
    )

    assert timeout.status_code == 504
    assert timeout.json()["code"] == "payment_timeout"
    with reliability_app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentRecord)) == 0
        assert session.scalar(select(func.count()).select_from(LedgerEntryRecord)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0

    retry = authorize(reliability_client, approved_payload, key=key)

    assert retry.status_code == 201
    assert "Idempotent-Replayed" not in retry.headers
    assert retry.json()["status"] == "AUTHORIZED"


def test_post_commit_timeout_recovers_original_response_without_duplicate(
    reliability_client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    key = "api-timeout-after-commit"
    timeout = authorize(
        reliability_client,
        approved_payload,
        key=key,
        failure="after_commit",
    )

    assert timeout.status_code == 504
    assert timeout.json() == {
        "code": "payment_timeout",
        "message": (
            "Payment outcome is uncertain; retry with the same idempotency key"
        ),
    }

    retry = authorize(reliability_client, approved_payload, key=key)

    assert retry.status_code == 200
    assert retry.headers["Idempotent-Replayed"] == "true"
    payment = retry.json()
    assert (payment["status"], payment["version"]) == ("AUTHORIZED", 1)
    ledger = reliability_client.get(f"/payments/{payment['id']}/ledger")
    assert [(entry["operation"], entry["amount"]) for entry in ledger.json()] == [
        ("AUTHORIZATION", 2500)
    ]


def test_post_commit_capture_timeout_is_safe_to_retry(
    reliability_client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    payment = authorize(
        reliability_client,
        approved_payload,
        key="api-authorize-before-capture-timeout",
    ).json()
    headers = {
        "Idempotency-Key": "api-capture-timeout-key",
        "X-Payment-Lab-Failure": "after_commit",
    }

    timeout = reliability_client.post(
        f"/payments/{payment['id']}/capture",
        headers=headers,
    )
    retry = reliability_client.post(
        f"/payments/{payment['id']}/capture",
        headers={"Idempotency-Key": "api-capture-timeout-key"},
    )

    assert timeout.status_code == 504
    assert retry.status_code == 200
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert (retry.json()["status"], retry.json()["version"]) == ("CAPTURED", 2)
    ledger = reliability_client.get(f"/payments/{payment['id']}/ledger").json()
    assert [entry["operation"] for entry in ledger] == ["AUTHORIZATION", "CAPTURE"]


def test_authorization_replay_returns_original_http_response_after_capture(
    reliability_client: TestClient,
    approved_payload: dict[str, object],
) -> None:
    authorization_key = "api-immutable-authorization"
    authorized = authorize(
        reliability_client,
        approved_payload,
        key=authorization_key,
    ).json()
    capture = reliability_client.post(
        f"/payments/{authorized['id']}/capture",
        headers={"Idempotency-Key": "api-capture-before-auth-replay"},
    )

    replay = authorize(
        reliability_client,
        approved_payload,
        key=authorization_key,
    )
    current = reliability_client.get(f"/payments/{authorized['id']}")

    assert capture.json()["status"] == "CAPTURED"
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == authorized
    assert (current.json()["status"], current.json()["version"]) == ("CAPTURED", 2)
