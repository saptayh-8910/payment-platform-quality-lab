"""Shared isolated application fixtures."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from payment_quality_lab.main import create_app


@pytest.fixture
def app(tmp_path) -> Iterator[FastAPI]:
    """Create an application backed by a new database for every test."""
    database_path = tmp_path / "payment-test.db"
    application = create_app(f"sqlite:///{database_path}")
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Expose the application through its real HTTP boundary."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def approved_payload() -> dict[str, object]:
    """Return a valid synthetic authorization request."""
    return {
        "merchant_reference": "order-2026-0001",
        "amount": 2500,
        "currency": "JPY",
        "payment_method_token": "tok_approved",
    }
