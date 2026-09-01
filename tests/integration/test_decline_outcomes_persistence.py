"""Cross-record evidence for detailed decline outcomes."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import AuthorizationDecision, Currency
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
)

DECLINE_CASES = [
    (AuthorizationDecision.DECLINE_INSUFFICIENT_FUNDS, "insufficient_funds"),
    (AuthorizationDecision.DECLINE_LIMIT_EXCEEDED, "limit_exceeded"),
    (AuthorizationDecision.DECLINE_EXPIRED, "expired_payment_method"),
    (AuthorizationDecision.DECLINE_VERIFICATION, "verification_failed"),
    (AuthorizationDecision.DECLINE_INVALID, "invalid_payment_method"),
    (AuthorizationDecision.DECLINE_UNKNOWN, "unknown"),
]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as database_session:
        yield database_session
    engine.dispose()


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.parametrize(("decision", "reason"), DECLINE_CASES)
def test_decline_reason_agrees_across_payment_idempotency_and_event(
    session: Session,
    decision: AuthorizationDecision,
    reason: str,
) -> None:
    outcome = authorize_payment(
        session,
        command=AuthorizationCommand(
            merchant_reference=f"integration-{reason}",
            amount=2500,
            currency=Currency.JPY,
            payment_method_token=decision,
        ),
        idempotency_key=f"integration-{reason}",
    )

    payment = session.get(PaymentRecord, outcome.payment.id)
    idempotency = session.get(IdempotencyRecord, f"integration-{reason}")
    event = session.scalar(
        select(WebhookEventRecord).where(
            WebhookEventRecord.payment_id == outcome.payment.id
        )
    )

    assert payment is not None
    assert idempotency is not None
    assert event is not None
    assert payment.status == "DECLINED"
    assert payment.decline_reason == reason
    assert (
        payment.authorized_amount,
        payment.captured_amount,
        payment.refunded_amount,
    ) == (
        0,
        0,
        0,
    )
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, IdempotencyRecord) == 1
    assert count(session, WebhookEventRecord) == 1

    snapshot = json.loads(idempotency.response_snapshot or "{}")
    payload = json.loads(event.payload)
    assert snapshot["decline_reason"] == reason
    assert payload["payment"]["decline_reason"] == reason
    retained = json.dumps({"snapshot": snapshot, "event": payload})
    assert decision.value not in retained


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("DECLINED", None),
        ("DECLINED", "not_recognized"),
        ("AUTHORIZED", "unknown"),
    ],
)
def test_database_rejects_reason_and_status_mismatch(
    session: Session,
    status: str,
    reason: str | None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        PaymentRecord(
            id=f"pay_invalid_{status}_{reason}",
            merchant_reference="invalid-decline-reason",
            amount=1000,
            currency="JPY",
            status=status,
            decline_reason=reason,
            authorized_amount=1000 if status == "AUTHORIZED" else 0,
            captured_amount=0,
            refunded_amount=0,
            version=1,
            created_at=now,
            updated_at=now,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
