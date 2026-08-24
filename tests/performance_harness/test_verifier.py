"""Tests for independent performance financial verification."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from payment_quality_lab.performance.profiles import (
    available_profiles,
    expected_payments,
    idempotency_key,
    reference,
)
from payment_quality_lab.performance.verifier import verify_database, write_report
from payment_quality_lab.persistence.database import Base, create_database_engine
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
    WebhookEventRecord,
)

RUN_ID = "20260823120000"


def seed_profile(database_url: str, profile: str) -> None:
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    timestamp = datetime(2026, 8, 23, 3, 0, tzinfo=UTC)
    with Session(engine) as session:
        for ordinal, expected in enumerate(expected_payments(profile)):
            payment_id = f"pay_{ordinal:036d}"
            approved_amount = expected.amount if expected.approved else 0
            payment = PaymentRecord(
                id=payment_id,
                merchant_reference=reference(RUN_ID, profile, expected),
                amount=expected.amount,
                currency=expected.currency,
                status="AUTHORIZED" if expected.approved else "DECLINED",
                authorized_amount=approved_amount,
                captured_amount=0,
                refunded_amount=0,
                version=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(payment)
            session.flush()
            session.add(
                IdempotencyRecord(
                    key=idempotency_key(RUN_ID, profile, expected),
                    request_fingerprint=f"{ordinal:064x}",
                    operation="AUTHORIZE",
                    payment_id=payment_id,
                    response_snapshot="{}",
                    created_at=timestamp,
                )
            )
            session.add(
                WebhookEventRecord(
                    id=f"evt_{ordinal:036d}",
                    payment_id=payment_id,
                    event_type=(
                        "payment.authorized"
                        if expected.approved
                        else "payment.declined"
                    ),
                    aggregate_version=1,
                    payload="{}",
                    status="PENDING",
                    attempt_count=0,
                    next_attempt_at=timestamp,
                    created_at=timestamp,
                )
            )
            if expected.approved:
                session.add(
                    LedgerEntryRecord(
                        id=f"led_{ordinal:036d}",
                        payment_id=payment_id,
                        operation="AUTHORIZATION",
                        amount=expected.amount,
                        currency=expected.currency,
                        created_at=timestamp,
                    )
                )
        session.commit()
    engine.dispose()


@pytest.mark.parametrize("profile", available_profiles())
def test_exact_profile_effects_pass(tmp_path: Path, profile: str) -> None:
    database_url = f"sqlite:///{tmp_path / 'performance.db'}"
    seed_profile(database_url, profile)

    report = verify_database(database_url, RUN_ID, profile)

    assert report.passed
    assert all(check.passed for check in report.checks)
    assert (
        set(report.currency_summary) == {"JPY", "USD"} or profile == "idempotent-burst"
    )


def test_missing_ledger_effect_fails_verification(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'performance.db'}"
    seed_profile(database_url, "smoke")
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        session.execute(delete(LedgerEntryRecord))
        session.commit()
    engine.dispose()

    report = verify_database(database_url, RUN_ID, "smoke")

    assert not report.passed
    failed_names = {check.name for check in report.checks if not check.passed}
    assert {"ledger count", "one ledger effect per approval"} <= failed_names


def test_report_is_sanitized_and_parseable(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'performance.db'}"
    seed_profile(database_url, "idempotent-burst")
    report = verify_database(database_url, RUN_ID, "idempotent-burst")
    output = tmp_path / "financial-verification.json"

    write_report(report, output)

    content = output.read_text(encoding="utf-8")
    assert '"passed": true' in content
    assert "-key" not in content
    assert "pay_" not in content
    assert "sqlite:///" not in content


def test_unknown_profile_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown performance profile"):
        verify_database(f"sqlite:///{tmp_path / 'unused.db'}", RUN_ID, "stress")
