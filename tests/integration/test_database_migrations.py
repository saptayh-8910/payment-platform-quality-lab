"""Integration evidence for explicit database schema upgrades."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from payment_quality_lab.domain.payment import AuthorizationDecision, Currency
from payment_quality_lab.main import create_app, create_runtime_app
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.migrations import (
    DatabaseSchemaError,
    current_revision,
    head_revision,
    require_current_schema,
    upgrade_database,
)
from payment_quality_lab.persistence.migrations import (
    run as run_migrations,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
)


def database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def test_fresh_migration_is_repeatable_and_supports_runtime_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "fresh.db"
    url = database_url(path)

    first_revision = upgrade_database(url)
    monkeypatch.setenv("PAYMENT_LAB_DATABASE_URL", url)
    run_migrations()
    assert "Database schema is current at revision" in capsys.readouterr().out
    repeat_engine = create_database_engine(url)
    second_revision = current_revision(repeat_engine)
    repeat_engine.dispose()

    engine = create_database_engine(url)
    assert first_revision == second_revision == head_revision()
    assert current_revision(engine) == head_revision()
    require_current_schema(engine)
    engine.dispose()

    app = create_runtime_app()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/checkout").status_code == 200
        response = client.post(
            "/payments",
            headers={"Idempotency-Key": "migration-fresh-0001"},
            json={
                "merchant_reference": "migration-fresh-order",
                "amount": 2500,
                "currency": "JPY",
                "payment_method_token": "tok_approved",
            },
        )
    app.state.engine.dispose()
    assert response.status_code == 201
    assert response.json()["status"] == "AUTHORIZED"


def test_runtime_rejects_an_unversioned_database_before_serving(
    tmp_path: Path,
) -> None:
    url = database_url(tmp_path / "unversioned.db")
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(
        DatabaseSchemaError,
        match="Run payment-quality-lab-migrate before starting the service",
    ):
        create_app(url, initialize_schema=False)


def test_unknown_unversioned_schema_is_not_marked_current(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE unexpected_data (id INTEGER PRIMARY KEY)")
        connection.commit()

    url = database_url(path)
    with pytest.raises(RuntimeError, match="Unsupported unversioned database tables"):
        upgrade_database(url)

    engine = create_database_engine(url)
    assert current_revision(engine) is None
    with pytest.raises(DatabaseSchemaError):
        require_current_schema(engine)
    engine.dispose()


def test_known_legacy_schema_is_upgraded_without_losing_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    url = database_url(path)
    approved = AuthorizationCommand(
        merchant_reference="legacy-approved-order",
        amount=2500,
        currency=Currency.JPY,
        payment_method_token=AuthorizationDecision.APPROVE,
    )
    declined = AuthorizationCommand(
        merchant_reference="legacy-declined-order",
        amount=3000,
        currency=Currency.JPY,
        payment_method_token=AuthorizationDecision.DECLINE,
    )
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        approved_payment = authorize_payment(
            session,
            command=approved,
            idempotency_key="legacy-approved-key",
        ).payment
        declined_payment = authorize_payment(
            session,
            command=declined,
            idempotency_key="legacy-declined-key",
        ).payment
        for payment in (approved_payment, declined_payment):
            event = session.scalar(
                select(WebhookEventRecord).where(
                    WebhookEventRecord.payment_id == payment.id
                )
            )
            assert event is not None
            session.add(
                MerchantPaymentProjectionRecord(
                    payment_id=payment.id,
                    merchant_reference=payment.merchant_reference,
                    amount=payment.amount,
                    currency=payment.currency,
                    status=payment.status,
                    decline_reason=payment.decline_reason,
                    authorized_amount=payment.authorized_amount,
                    captured_amount=payment.captured_amount,
                    refunded_amount=payment.refunded_amount,
                    aggregate_version=payment.version,
                    last_event_id=event.id,
                    updated_at=payment.updated_at,
                )
            )
        session.commit()
        approved_id = approved_payment.id
        declined_id = declined_payment.id
    engine.dispose()

    rebuild_as_known_legacy(path)
    assert upgrade_database(url) == head_revision()

    engine = create_database_engine(url)
    schema = inspect(engine)
    assert {column["name"] for column in schema.get_columns("payments")} >= {
        "decline_reason"
    }
    assert {column["name"] for column in schema.get_columns("idempotency_records")} >= {
        "operation",
        "response_snapshot",
    }
    with create_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(PaymentRecord)) == 2
        assert session.scalar(select(func.count()).select_from(LedgerEntryRecord)) == 1
        assert session.scalar(select(func.count()).select_from(WebhookEventRecord)) == 2
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2
        assert (
            session.scalar(
                select(func.count()).select_from(MerchantPaymentProjectionRecord)
            )
            == 2
        )
        assert session.get(PaymentRecord, declined_id).decline_reason == "unknown"
        declined_projection = session.get(MerchantPaymentProjectionRecord, declined_id)
        assert declined_projection.decline_reason == "unknown"
        claims = list(session.scalars(select(IdempotencyRecord)))
        assert {claim.operation for claim in claims} == {"AUTHORIZE"}
        assert all(claim.response_snapshot is not None for claim in claims)
    engine.dispose()

    app = create_app(url, initialize_schema=False)
    with TestClient(app) as client:
        replay = client.post(
            "/payments",
            headers={"Idempotency-Key": "legacy-approved-key"},
            json={
                "merchant_reference": approved.merchant_reference,
                "amount": approved.amount,
                "currency": approved.currency.value,
                "payment_method_token": "tok_approved",
            },
        )
    app.state.engine.dispose()
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == approved_id


def rebuild_as_known_legacy(path: Path) -> None:
    """Remove fields absent from the real pre-migration local schema."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.executescript(
            """
            CREATE TABLE payments_legacy (
                id VARCHAR(40) NOT NULL PRIMARY KEY,
                merchant_reference VARCHAR(64) NOT NULL,
                amount INTEGER NOT NULL,
                currency VARCHAR(3) NOT NULL,
                status VARCHAR(32) NOT NULL,
                authorized_amount INTEGER NOT NULL,
                captured_amount INTEGER NOT NULL,
                refunded_amount INTEGER NOT NULL,
                version INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO payments_legacy
            SELECT id, merchant_reference, amount, currency, status,
                   authorized_amount, captured_amount, refunded_amount,
                   version, created_at, updated_at
            FROM payments;
            DROP TABLE payments;
            ALTER TABLE payments_legacy RENAME TO payments;
            CREATE INDEX ix_payments_merchant_reference
                ON payments (merchant_reference);
            CREATE INDEX ix_payments_status ON payments (status);

            CREATE TABLE idempotency_records_legacy (
                "key" VARCHAR(128) NOT NULL PRIMARY KEY,
                request_fingerprint VARCHAR(64) NOT NULL,
                payment_id VARCHAR(40) NOT NULL UNIQUE,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(payment_id) REFERENCES payments (id)
            );
            INSERT INTO idempotency_records_legacy
            SELECT "key", request_fingerprint, payment_id, created_at
            FROM idempotency_records;
            DROP TABLE idempotency_records;
            ALTER TABLE idempotency_records_legacy RENAME TO idempotency_records;

            CREATE TABLE merchant_payment_projections_legacy (
                payment_id VARCHAR(40) NOT NULL PRIMARY KEY,
                merchant_reference VARCHAR(64) NOT NULL,
                amount INTEGER NOT NULL,
                currency VARCHAR(3) NOT NULL,
                status VARCHAR(32) NOT NULL,
                authorized_amount INTEGER NOT NULL,
                captured_amount INTEGER NOT NULL,
                refunded_amount INTEGER NOT NULL,
                aggregate_version INTEGER NOT NULL,
                last_event_id VARCHAR(40) NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO merchant_payment_projections_legacy
            SELECT payment_id, merchant_reference, amount, currency, status,
                   authorized_amount, captured_amount, refunded_amount,
                   aggregate_version, last_event_id, updated_at
            FROM merchant_payment_projections;
            DROP TABLE merchant_payment_projections;
            ALTER TABLE merchant_payment_projections_legacy
                RENAME TO merchant_payment_projections;
            CREATE INDEX ix_merchant_payment_projections_merchant_reference
                ON merchant_payment_projections (merchant_reference);
            CREATE INDEX ix_merchant_payment_projections_status
                ON merchant_payment_projections (status);
            """
        )
