"""Cross-record evidence for authenticated payment confirmations."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import Currency, DelayedPaymentDecision
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    PaymentConfirmationRecord,
    PaymentRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services import confirmations
from payment_quality_lab.services.confirmations import (
    ConfirmationCommand,
    ConfirmationDisposition,
    process_confirmation,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
)
from payment_quality_lab.services.reconciliation import (
    SettlementCurrency,
    SettlementInput,
    create_settlement_batch,
    reconcile_settlement_batch,
)
from payment_quality_lab.services.webhooks import consume_webhook, sign_webhook

CREATED_AT = datetime(2026, 9, 9, 3, 0, tzinfo=UTC)
RECEIVED_AT = CREATED_AT + timedelta(hours=1)
WEBHOOK_SECRET = "whsec_confirmation_reconciliation"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with create_session_factory(engine)() as database_session:
        yield database_session
    engine.dispose()


def create_delayed_payment(session: Session) -> PaymentRecord:
    return authorize_payment(
        session,
        command=AuthorizationCommand(
            merchant_reference="confirmation-integration-order",
            amount=2500,
            currency=Currency.JPY,
            payment_method_token=DelayedPaymentDecision.AWAIT_CONFIRMATION,
        ),
        idempotency_key="confirmation-integration-create",
        clock=lambda: CREATED_AT,
    ).payment  # type: ignore[return-value]


def command(
    payment_reference: str,
    *,
    confirmation_id: str = "cnf_integration_0001",
    amount: int = 2500,
    currency: Currency = Currency.JPY,
) -> ConfirmationCommand:
    return ConfirmationCommand(
        confirmation_id=confirmation_id,
        payment_reference=payment_reference,
        amount=amount,
        currency=currency,
    )


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_conf_02_capture_commits_inbox_ledger_payment_and_event_together(
    session: Session,
) -> None:
    payment = create_delayed_payment(session)

    outcome = process_confirmation(
        session,
        command=command(payment.payment_reference or ""),
        received_at=RECEIVED_AT,
    )

    stored_payment = session.get(PaymentRecord, payment.id)
    assert outcome.replayed is False
    assert outcome.confirmation.disposition == ConfirmationDisposition.APPLIED.value
    assert stored_payment is not None
    assert stored_payment.status == "CAPTURED"
    assert stored_payment.authorized_amount == stored_payment.captured_amount == 2500
    assert stored_payment.version == 2
    assert count(session, PaymentConfirmationRecord) == 1
    assert count(session, LedgerEntryRecord) == 1
    assert count(session, WebhookEventRecord) == 2
    ledger = session.scalar(select(LedgerEntryRecord))
    assert ledger is not None
    assert ledger.operation == "CONFIRMATION_CAPTURE"
    events = list(
        session.scalars(
            select(WebhookEventRecord).order_by(WebhookEventRecord.aggregate_version)
        )
    )
    assert [(event.event_type, event.aggregate_version) for event in events] == [
        ("payment.confirmation_requested", 1),
        ("payment.captured", 2),
    ]


def test_conf_02_event_failure_rolls_back_every_confirmation_effect(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = create_delayed_payment(session)

    def fail_event(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated event failure")

    monkeypatch.setattr(confirmations, "create_outbox_event", fail_event)

    with pytest.raises(RuntimeError, match="simulated event failure"):
        process_confirmation(
            session,
            command=command(payment.payment_reference or ""),
            received_at=RECEIVED_AT,
        )

    stored_payment = session.get(PaymentRecord, payment.id)
    assert stored_payment is not None
    assert stored_payment.status == "AWAITING_PAYMENT"
    assert stored_payment.authorized_amount == stored_payment.captured_amount == 0
    assert stored_payment.version == 1
    assert count(session, PaymentConfirmationRecord) == 0
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, WebhookEventRecord) == 1


def test_dup_03_anomalous_replay_keeps_one_queryable_record(
    session: Session,
) -> None:
    payment = create_delayed_payment(session)
    mismatch = command(payment.payment_reference or "", amount=2499)
    first = process_confirmation(
        session,
        command=mismatch,
        received_at=RECEIVED_AT,
    )
    replay = process_confirmation(
        session,
        command=mismatch,
        received_at=RECEIVED_AT + timedelta(minutes=1),
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert first.confirmation.confirmation_id == replay.confirmation.confirmation_id
    assert replay.confirmation.received_at == first.confirmation.received_at
    assert replay.confirmation.disposition == "amount_mismatch"
    assert count(session, PaymentConfirmationRecord) == 1
    assert count(session, LedgerEntryRecord) == 0
    assert count(session, WebhookEventRecord) == 1


def test_late_confirmations_create_one_expiry_event_and_separate_evidence(
    session: Session,
) -> None:
    payment = create_delayed_payment(session)
    boundary = CREATED_AT + timedelta(hours=72)
    first = process_confirmation(
        session,
        command=command(payment.payment_reference or ""),
        received_at=boundary,
    )
    second = process_confirmation(
        session,
        command=command(
            payment.payment_reference or "",
            confirmation_id="cnf_integration_0002",
        ),
        received_at=boundary + timedelta(seconds=1),
    )

    assert first.confirmation.disposition == "late"
    assert second.confirmation.disposition == "late"
    assert count(session, PaymentConfirmationRecord) == 2
    assert count(session, LedgerEntryRecord) == 0
    events = list(session.scalars(select(WebhookEventRecord)))
    assert [event.event_type for event in events].count("payment.expired") == 1
    assert session.get(PaymentRecord, payment.id).status == "EXPIRED"


def test_priv_c01_retained_confirmation_evidence_is_minimal(
    session: Session,
) -> None:
    payment = create_delayed_payment(session)
    supplied = command(payment.payment_reference or "")

    process_confirmation(
        session,
        command=supplied,
        received_at=RECEIVED_AT,
    )

    stored = session.get(PaymentConfirmationRecord, supplied.confirmation_id)
    assert stored is not None
    retained = " ".join(
        str(value)
        for value in (
            stored.confirmation_id,
            stored.request_fingerprint,
            stored.payment_reference,
            stored.amount,
            stored.currency,
            stored.received_at,
            stored.disposition,
            stored.payment_id,
            stored.response_snapshot,
        )
    )
    assert "cnfsec_" not in retained
    assert "Confirmation-Signature" not in retained
    assert stored.response_snapshot == '{"accepted":true}'


def test_unknown_reference_evidence_has_no_payment_foreign_key(
    session: Session,
) -> None:
    outcome = process_confirmation(
        session,
        command=command("ref_" + ("f" * 32)),
        received_at=RECEIVED_AT,
    )

    assert outcome.confirmation.disposition == "unknown_reference"
    assert outcome.confirmation.payment_id is None
    assert count(session, PaymentRecord) == 0
    assert count(session, PaymentConfirmationRecord) == 1


def test_rec_c03_confirmation_capture_reconciles_across_all_sources(
    session: Session,
) -> None:
    payment = create_delayed_payment(session)
    process_confirmation(
        session,
        command=command(payment.payment_reference or ""),
        received_at=RECEIVED_AT,
    )
    events = list(
        session.scalars(
            select(WebhookEventRecord).order_by(WebhookEventRecord.aggregate_version)
        )
    )
    delivery_time = RECEIVED_AT + timedelta(seconds=1)
    for event in events:
        body = event.payload.encode()
        signature = sign_webhook(
            body,
            secret=WEBHOOK_SECRET,
            timestamp=int(delivery_time.timestamp()),
        )
        consume_webhook(
            session,
            payload=body,
            signature_header=signature,
            secret=WEBHOOK_SECRET,
            now=delivery_time,
        )

    batch = create_settlement_batch(
        session,
        cutoff=RECEIVED_AT + timedelta(seconds=2),
        entries=[
            SettlementInput(
                payment_id=payment.id,
                amount=2500,
                currency=SettlementCurrency.JPY,
            )
        ],
    )
    report = reconcile_settlement_batch(session, batch_id=batch.id)

    assert report.summary.status.value == "matched"
    item = next(item for item in report.items if item.payment_id == payment.id)
    assert item.ledger_authorized_amount == 2500
    assert item.ledger_captured_amount == 2500
    assert item.projection_status.value == "matched"
    assert item.settlement_classification.value == "matched"
