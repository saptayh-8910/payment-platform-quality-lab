"""Cross-record evidence for asynchronous payment creation."""

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import (
    Currency,
    DelayedPaymentDecision,
)
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
    IdempotencyConflictError,
    authorize_payment,
)
from payment_quality_lab.services.webhooks import (
    ConsumerDisposition,
    consume_webhook,
    get_merchant_projection,
    sign_webhook,
)

FIXED_NOW = datetime(2026, 9, 4, 4, 30, tzinfo=UTC)
SECRET = "whsec_async_creation_test"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as database_session:
        yield database_session


def delayed_command(**changes: object) -> AuthorizationCommand:
    values = {
        "merchant_reference": "async-integration-order",
        "amount": 2500,
        "currency": Currency.JPY,
        "payment_method_token": DelayedPaymentDecision.AWAIT_CONFIRMATION,
    }
    values.update(changes)
    return AuthorizationCommand(**values)  # type: ignore[arg-type]


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_conf_01_creation_is_atomic_private_and_has_no_financial_effect(
    session: Session,
) -> None:
    command = delayed_command()

    outcome = authorize_payment(
        session,
        command=command,
        idempotency_key="async-integration-key-0001",
        clock=lambda: FIXED_NOW,
    )

    payment = outcome.payment
    assert outcome.replayed is False
    assert payment.status == "AWAITING_PAYMENT"
    assert payment.payment_flow == "ASYNCHRONOUS_CONFIRMATION"
    assert re.fullmatch(r"ref_[0-9a-f]{32}", payment.payment_reference or "")
    assert payment.expires_at == FIXED_NOW + timedelta(hours=72)
    assert (payment.authorized_amount, payment.captured_amount) == (0, 0)
    assert payment.refunded_amount == 0
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, IdempotencyRecord) == 1
    assert count(session, WebhookEventRecord) == 1

    claim = session.get(IdempotencyRecord, "async-integration-key-0001")
    event = session.scalar(select(WebhookEventRecord))
    assert claim is not None
    assert event is not None
    assert event.event_type == "payment.confirmation_requested"
    retained_evidence = claim.response_snapshot + event.payload
    assert command.payment_method_token.value not in retained_evidence
    payload = json.loads(event.payload)
    assert payload["payment"]["payment_reference"] == payment.payment_reference
    assert payload["payment"]["expires_at"] == "2026-09-07T04:30:00Z"


def test_conf_04_replay_preserves_reference_expiry_and_record_counts(
    session: Session,
) -> None:
    command = delayed_command()
    first = authorize_payment(
        session,
        command=command,
        idempotency_key="async-integration-replay-key",
        clock=lambda: FIXED_NOW,
    )

    replay = authorize_payment(
        session,
        command=command,
        idempotency_key="async-integration-replay-key",
        clock=lambda: FIXED_NOW + timedelta(days=2),
    )

    assert replay.replayed is True
    assert replay.payment.id == first.payment.id
    assert replay.payment.payment_reference == first.payment.payment_reference
    assert replay.payment.expires_at == first.payment.expires_at
    assert replay.payment.created_at == first.payment.created_at
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, IdempotencyRecord) == 1
    assert count(session, WebhookEventRecord) == 1


def test_conf_04_conflicting_payload_preserves_original_records(
    session: Session,
) -> None:
    first = authorize_payment(
        session,
        command=delayed_command(),
        idempotency_key="async-integration-conflict-key",
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(IdempotencyConflictError):
        authorize_payment(
            session,
            command=delayed_command(amount=2501),
            idempotency_key="async-integration-conflict-key",
            clock=lambda: FIXED_NOW,
        )

    assert session.get(PaymentRecord, first.payment.id).amount == 2500
    assert count(session, PaymentRecord) == 1
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, IdempotencyRecord) == 1
    assert count(session, WebhookEventRecord) == 1


def test_confirmation_requested_event_builds_matching_merchant_projection(
    session: Session,
) -> None:
    payment = authorize_payment(
        session,
        command=delayed_command(),
        idempotency_key="async-integration-projection-key",
        clock=lambda: FIXED_NOW,
    ).payment
    event = session.scalar(select(WebhookEventRecord))
    assert event is not None
    body = event.payload.encode()
    received_at = FIXED_NOW + timedelta(seconds=1)
    signature = sign_webhook(
        body,
        secret=SECRET,
        timestamp=int(received_at.timestamp()),
    )

    outcome = consume_webhook(
        session,
        payload=body,
        signature_header=signature,
        secret=SECRET,
        now=received_at,
    )
    projection = get_merchant_projection(session, payment.id)

    assert outcome.disposition is ConsumerDisposition.APPLIED
    assert projection is not None
    assert projection.status == "AWAITING_PAYMENT"
    assert projection.payment_flow == "ASYNCHRONOUS_CONFIRMATION"
    assert projection.payment_reference == payment.payment_reference
    assert projection.expires_at is not None
    assert projection.expires_at.replace(tzinfo=UTC) == payment.expires_at

    repeated_version = json.loads(event.payload)
    repeated_version["id"] = "evt_redundant_async_snapshot"
    repeated_body = json.dumps(
        repeated_version, separators=(",", ":"), sort_keys=True
    ).encode()
    repeated_signature = sign_webhook(
        repeated_body,
        secret=SECRET,
        timestamp=int(received_at.timestamp()),
    )
    redundant = consume_webhook(
        session,
        payload=repeated_body,
        signature_header=repeated_signature,
        secret=SECRET,
        now=received_at,
    )

    assert redundant.disposition is ConsumerDisposition.REDUNDANT


def test_injected_clock_must_be_timezone_aware(session: Session) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        authorize_payment(
            session,
            command=delayed_command(),
            idempotency_key="async-naive-clock-key",
            clock=lambda: datetime(2026, 9, 4, 4, 30),
        )

    assert count(session, PaymentRecord) == 0
    assert count(session, IdempotencyRecord) == 0
