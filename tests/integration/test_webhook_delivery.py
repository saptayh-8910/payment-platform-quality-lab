"""Integration evidence for webhook outbox, delivery, and consumption."""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from payment_quality_lab.domain.payment import (
    AuthorizationDecision,
    Currency,
    InvalidPaymentTransitionError,
)
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    ProcessedWebhookRecord,
    WebhookDeliveryAttemptRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services import payments as payment_service
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    FailurePoint,
    SimulatedPaymentTimeoutError,
    authorize_payment,
    cancel_payment,
    capture_payment,
    refund_payment,
)
from payment_quality_lab.services.webhooks import (
    ConsumerDisposition,
    DeliveryFault,
    SimulatedConsumerPersistenceError,
    WebhookDeliveryNotReadyError,
    WebhookEventCollisionError,
    WebhookStatus,
    WebhookVersionConflictError,
    consume_webhook,
    dispatch_webhook,
    get_delivery_attempts,
    get_merchant_projection,
    get_webhook_events,
    sign_webhook,
)

SECRET = "whsec_integration_synthetic"


@pytest.fixture
def factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'webhooks.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def command() -> AuthorizationCommand:
    return AuthorizationCommand(
        merchant_reference="webhook-order-001",
        amount=1000,
        currency=Currency.JPY,
        payment_method_token=AuthorizationDecision.APPROVE,
    )


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def authorize_once(
    factory: sessionmaker[Session],
    command: AuthorizationCommand,
    *,
    key: str = "webhook-authorize-key",
) -> str:
    with factory() as session:
        return authorize_payment(
            session,
            command=command,
            idempotency_key=key,
        ).payment.id


def event_now(event: WebhookEventRecord, seconds: int = 1) -> datetime:
    created = event.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created + timedelta(seconds=seconds)


def consumer_receiver(factory: sessionmaker[Session]):
    def receive(payload: bytes, signature: str, now: datetime) -> int:
        with factory() as consumer_session:
            consume_webhook(
                consumer_session,
                payload=payload,
                signature_header=signature,
                secret=SECRET,
                now=now,
            )
        return 200

    return receive


def signed_event(event: WebhookEventRecord, now: datetime) -> tuple[bytes, str]:
    payload = event.payload.encode()
    signature = sign_webhook(
        payload,
        secret=SECRET,
        timestamp=int(now.timestamp()),
    )
    return payload, signature


def test_lifecycle_commits_one_full_snapshot_event_per_version(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="webhook-capture-key",
        )
        refund_payment(
            session,
            payment_id=payment_id,
            amount=400,
            idempotency_key="webhook-partial-refund-key",
        )
        refund_payment(
            session,
            payment_id=payment_id,
            amount=600,
            idempotency_key="webhook-full-refund-key",
        )
        events = sorted(
            get_webhook_events(session), key=lambda event: event.aggregate_version
        )

    assert [(event.event_type, event.aggregate_version) for event in events] == [
        ("payment.authorized", 1),
        ("payment.captured", 2),
        ("payment.refunded", 3),
        ("payment.refunded", 4),
    ]
    assert len({event.id for event in events}) == 4
    final_payload = json.loads(events[-1].payload)
    assert final_payload["payment"]["status"] == "REFUNDED"
    assert final_payload["payment"]["refunded_amount"] == 1000
    assert final_payload["payment"]["version"] == 4
    assert "payment_method_token" not in events[0].payload
    assert "whsec" not in events[0].payload


def test_decline_and_cancellation_create_correct_events(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    declined = AuthorizationCommand(
        merchant_reference="declined-webhook-order",
        amount=command.amount,
        currency=command.currency,
        payment_method_token=AuthorizationDecision.DECLINE,
    )
    with factory() as session:
        authorize_payment(
            session,
            command=declined,
            idempotency_key="webhook-decline-key",
        )
        approved_id = authorize_payment(
            session,
            command=command,
            idempotency_key="webhook-authorize-cancel-key",
        ).payment.id
        cancel_payment(
            session,
            payment_id=approved_id,
            idempotency_key="webhook-cancel-key",
        )
        events = get_webhook_events(session)

    assert sorted(event.event_type for event in events) == [
        "payment.authorized",
        "payment.cancelled",
        "payment.declined",
    ]


def test_rejected_operation_and_idempotent_replay_create_no_event(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        first = capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="webhook-capture-replay-key",
        )
        replay = capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="webhook-capture-replay-key",
        )
        with pytest.raises(InvalidPaymentTransitionError):
            capture_payment(
                session,
                payment_id=payment_id,
                idempotency_key="webhook-rejected-capture-key",
            )
        events = get_webhook_events(session)

    assert first.replayed is False
    assert replay.replayed is True
    assert len(events) == 2


def test_payment_timeout_boundaries_keep_outbox_atomic(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    with factory() as session:
        with pytest.raises(SimulatedPaymentTimeoutError):
            authorize_payment(
                session,
                command=command,
                idempotency_key="webhook-before-commit-key",
                failure_point=FailurePoint.BEFORE_COMMIT,
            )
        assert count(session, WebhookEventRecord) == 0

        with pytest.raises(SimulatedPaymentTimeoutError):
            authorize_payment(
                session,
                command=command,
                idempotency_key="webhook-after-commit-key",
                failure_point=FailurePoint.AFTER_COMMIT,
            )
        retry = authorize_payment(
            session,
            command=command,
            idempotency_key="webhook-after-commit-key",
        )

        assert retry.replayed is True
        assert count(session, PaymentRecord) == 1
        assert count(session, LedgerEntryRecord) == 1
        assert count(session, IdempotencyRecord) == 1
        assert count(session, WebhookEventRecord) == 1


def test_outbox_failure_rolls_back_complete_financial_outcome(
    factory: sessionmaker[Session],
    command: AuthorizationCommand,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_outbox(*_args, **_kwargs):
        raise RuntimeError("simulated outbox persistence failure")

    monkeypatch.setattr(payment_service, "create_outbox_event", fail_outbox)
    with factory() as session:
        with pytest.raises(RuntimeError, match="outbox persistence failure"):
            authorize_payment(
                session,
                command=command,
                idempotency_key="webhook-outbox-failure-key",
            )

        assert count(session, PaymentRecord) == 0
        assert count(session, LedgerEntryRecord) == 0
        assert count(session, IdempotencyRecord) == 0
        assert count(session, WebhookEventRecord) == 0


def test_concurrent_equivalent_authorizations_create_one_event(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    barrier = Barrier(2)

    def submit() -> bool:
        with factory() as session:
            barrier.wait()
            return authorize_payment(
                session,
                command=command,
                idempotency_key="webhook-concurrent-key",
            ).replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert sorted(results) == [False, True]
    with factory() as session:
        assert count(session, PaymentRecord) == 1
        assert count(session, WebhookEventRecord) == 1


def test_consumer_applies_first_event_and_ignores_exact_duplicate(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        now = event_now(event)
        payload, signature = signed_event(event, now)
        first = consume_webhook(
            session,
            payload=payload,
            signature_header=signature,
            secret=SECRET,
            now=now,
        )
        duplicate = consume_webhook(
            session,
            payload=payload,
            signature_header=signature,
            secret=SECRET,
            now=now,
        )
        projection = get_merchant_projection(session, payment_id)

    assert first.disposition is ConsumerDisposition.APPLIED
    assert duplicate.disposition is ConsumerDisposition.DUPLICATE
    assert duplicate.duplicate is True
    assert projection is not None
    assert (projection.status, projection.aggregate_version) == ("AUTHORIZED", 1)


def test_newer_full_snapshot_applies_before_older_event(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="webhook-out-of-order-capture",
        )
        events = sorted(
            get_webhook_events(session), key=lambda event: event.aggregate_version
        )
        authorization, capture = events
        now = event_now(capture)
        capture_payload, capture_signature = signed_event(capture, now)
        authorization_payload, authorization_signature = signed_event(
            authorization, now
        )

        newer = consume_webhook(
            session,
            payload=capture_payload,
            signature_header=capture_signature,
            secret=SECRET,
            now=now,
        )
        older = consume_webhook(
            session,
            payload=authorization_payload,
            signature_header=authorization_signature,
            secret=SECRET,
            now=now,
        )
        projection = get_merchant_projection(session, payment_id)

    assert newer.disposition is ConsumerDisposition.APPLIED
    assert newer.version_gap is True
    assert older.disposition is ConsumerDisposition.STALE
    assert projection is not None
    assert (projection.status, projection.aggregate_version) == ("CAPTURED", 2)


def test_event_id_collision_and_version_conflict_are_rejected(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        now = event_now(event)
        original, original_signature = signed_event(event, now)
        consume_webhook(
            session,
            payload=original,
            signature_header=original_signature,
            secret=SECRET,
            now=now,
        )
        changed = json.loads(original)
        changed["payment"]["merchant_reference"] = "changed-order"
        collision_body = json.dumps(
            changed, separators=(",", ":"), sort_keys=True
        ).encode()
        collision_signature = sign_webhook(
            collision_body,
            secret=SECRET,
            timestamp=int(now.timestamp()),
        )
        with pytest.raises(WebhookEventCollisionError):
            consume_webhook(
                session,
                payload=collision_body,
                signature_header=collision_signature,
                secret=SECRET,
                now=now,
            )

        changed["id"] = "evt_conflicting_version"
        conflict_body = json.dumps(
            changed, separators=(",", ":"), sort_keys=True
        ).encode()
        conflict_signature = sign_webhook(
            conflict_body,
            secret=SECRET,
            timestamp=int(now.timestamp()),
        )
        with pytest.raises(WebhookVersionConflictError):
            consume_webhook(
                session,
                payload=conflict_body,
                signature_header=conflict_signature,
                secret=SECRET,
                now=now,
            )


def test_consumer_failure_rolls_back_inbox_and_projection(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        now = event_now(event)
        payload, signature = signed_event(event, now)
        with pytest.raises(SimulatedConsumerPersistenceError):
            consume_webhook(
                session,
                payload=payload,
                signature_header=signature,
                secret=SECRET,
                now=now,
                fail_after_inbox=True,
            )
        assert count(session, ProcessedWebhookRecord) == 0
        assert count(session, MerchantPaymentProjectionRecord) == 0

        retry = consume_webhook(
            session,
            payload=payload,
            signature_header=signature,
            secret=SECRET,
            now=now,
        )

    assert retry.disposition is ConsumerDisposition.APPLIED


def test_concurrent_duplicate_deliveries_apply_consumer_effect_once(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        now = event_now(event)
        payload, signature = signed_event(event, now)
    barrier = Barrier(2)

    def submit() -> ConsumerDisposition:
        with factory() as consumer_session:
            barrier.wait()
            return consume_webhook(
                consumer_session,
                payload=payload,
                signature_header=signature,
                secret=SECRET,
                now=now,
            ).disposition

    with ThreadPoolExecutor(max_workers=2) as executor:
        dispositions = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert sorted(disposition.value for disposition in dispositions) == [
        "APPLIED",
        "DUPLICATE",
    ]
    with factory() as session:
        assert count(session, ProcessedWebhookRecord) == 1
        assert count(session, MerchantPaymentProjectionRecord) == 1


def test_successful_delivery_records_attempt_and_projection(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        result = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=consumer_receiver(factory),
            now=event_now(event),
        )
        attempts = get_delivery_attempts(session, event.id)
        projection = get_merchant_projection(session, payment_id)

    assert result.status is WebhookStatus.DELIVERED
    assert result.response_status == 200
    assert [(attempt.outcome, attempt.response_status) for attempt in attempts] == [
        ("SUCCESS", 200)
    ]
    assert projection is not None


def test_transient_failure_uses_deterministic_retry_schedule(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)
    responses = iter([503, 200])

    def receiver(_payload: bytes, _signature: str, _now: datetime) -> int:
        return next(responses)

    with factory() as session:
        event = get_webhook_events(session)[0]
        first_time = event_now(event)
        first = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=receiver,
            now=first_time,
        )
        assert first.next_attempt_at == first_time + timedelta(seconds=1)
        with pytest.raises(WebhookDeliveryNotReadyError):
            dispatch_webhook(
                session,
                event_id=event.id,
                secret=SECRET,
                receiver=receiver,
                now=first_time,
            )
        second = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=receiver,
            now=first_time + timedelta(seconds=1),
        )

    assert first.status is WebhookStatus.PENDING
    assert first.outcome == "HTTP_ERROR"
    assert second.status is WebhookStatus.DELIVERED


@pytest.mark.parametrize(
    ("fault", "receiver", "expected_outcome"),
    [
        (DeliveryFault.BEFORE_DELIVERY, lambda *_args: 200, "TIMEOUT"),
        (
            None,
            lambda *_args: (_ for _ in ()).throw(ConnectionError()),
            "CONNECTION_ERROR",
        ),
    ],
)
def test_transport_failures_are_recorded_for_retry(
    factory: sessionmaker[Session],
    command: AuthorizationCommand,
    fault: DeliveryFault | None,
    receiver,
    expected_outcome: str,
) -> None:
    authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        result = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=receiver,
            now=event_now(event),
            fault=fault,
        )

    assert result.outcome == expected_outcome
    assert result.status is WebhookStatus.PENDING
    assert result.response_status is None


def test_persistent_failure_exhausts_after_three_attempts(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)

    def unavailable(_payload: bytes, _signature: str, _now: datetime) -> int:
        return 503

    with factory() as session:
        event = get_webhook_events(session)[0]
        first_time = event_now(event)
        first = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=unavailable,
            now=first_time,
        )
        second = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=unavailable,
            now=first_time + timedelta(seconds=1),
        )
        third = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=unavailable,
            now=first_time + timedelta(seconds=6),
        )
        attempts = get_delivery_attempts(session, event.id)

    assert first.next_attempt_at == first_time + timedelta(seconds=1)
    assert second.next_attempt_at == first_time + timedelta(seconds=6)
    assert third.status is WebhookStatus.EXHAUSTED
    assert third.next_attempt_at is None
    assert [attempt.attempt_number for attempt in attempts] == [1, 2, 3]


def test_acknowledgement_loss_redelivers_without_duplicate_effect(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        first_time = event_now(event)
        lost = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=consumer_receiver(factory),
            now=first_time,
            fault=DeliveryFault.ACK_LOST_AFTER_CONSUMER,
        )
        recovered = dispatch_webhook(
            session,
            event_id=event.id,
            secret=SECRET,
            receiver=consumer_receiver(factory),
            now=first_time + timedelta(seconds=1),
        )
        attempts = get_delivery_attempts(session, event.id)
        projection = get_merchant_projection(session, payment_id)

    assert lost.status is WebhookStatus.PENDING
    assert lost.outcome == "TIMEOUT"
    assert recovered.status is WebhookStatus.DELIVERED
    assert [(attempt.outcome, attempt.response_status) for attempt in attempts] == [
        ("TIMEOUT", None),
        ("SUCCESS", 200),
    ]
    assert projection is not None
    with factory() as session:
        assert count(session, ProcessedWebhookRecord) == 1
        assert count(session, MerchantPaymentProjectionRecord) == 1
        assert count(session, PaymentRecord) == 1
        assert count(session, LedgerEntryRecord) == 1


def test_concurrent_dispatchers_create_one_active_attempt(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    authorize_once(factory, command)
    with factory() as session:
        event = get_webhook_events(session)[0]
        event_id = event.id
        now = event_now(event)
    barrier = Barrier(2)

    def submit():
        with factory() as delivery_session:
            barrier.wait()
            try:
                return dispatch_webhook(
                    delivery_session,
                    event_id=event_id,
                    secret=SECRET,
                    receiver=lambda *_args: 200,
                    now=now,
                )
            except WebhookDeliveryNotReadyError as error:
                return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result() for future in [executor.submit(submit) for _ in range(2)]
        ]

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert (
        sum(isinstance(outcome, WebhookDeliveryNotReadyError) for outcome in outcomes)
        == 1
    )
    with factory() as session:
        event = session.get(WebhookEventRecord, event_id)
        assert event is not None
        assert event.status == "DELIVERED"
        assert event.attempt_count == 1
        assert count(session, WebhookDeliveryAttemptRecord) == 1


def test_failed_event_does_not_block_another_ready_event(
    factory: sessionmaker[Session], command: AuthorizationCommand
) -> None:
    payment_id = authorize_once(factory, command)
    with factory() as session:
        capture_payment(
            session,
            payment_id=payment_id,
            idempotency_key="webhook-second-ready-event",
        )
        events = sorted(
            get_webhook_events(session), key=lambda event: event.aggregate_version
        )
        first, second = events
        now = max(event_now(first), event_now(second))
        failed = dispatch_webhook(
            session,
            event_id=first.id,
            secret=SECRET,
            receiver=lambda *_args: 503,
            now=now,
        )
        delivered = dispatch_webhook(
            session,
            event_id=second.id,
            secret=SECRET,
            receiver=consumer_receiver(factory),
            now=now,
        )

    assert failed.status is WebhookStatus.PENDING
    assert delivered.status is WebhookStatus.DELIVERED
