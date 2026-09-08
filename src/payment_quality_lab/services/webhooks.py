"""Transactional webhook outbox, delivery, signing, and consumer services."""

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from payment_quality_lab.domain.payment import (
    Currency,
    DeclineReason,
    PaymentFlow,
    PaymentState,
    PaymentStatus,
)
from payment_quality_lab.persistence.models import (
    MerchantPaymentProjectionRecord,
    PaymentRecord,
    ProcessedWebhookRecord,
    WebhookDeliveryAttemptRecord,
    WebhookEventRecord,
)

SIGNATURE_TOLERANCE_SECONDS = 300
MAX_DELIVERY_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (1, 5)
DELIVERY_LEASE_SECONDS = 30


class WebhookEventType(StrEnum):
    """Payment changes exposed to the simulated merchant consumer."""

    AUTHORIZED = "payment.authorized"
    CONFIRMATION_REQUESTED = "payment.confirmation_requested"
    DECLINED = "payment.declined"
    CAPTURED = "payment.captured"
    CANCELLED = "payment.cancelled"
    REFUNDED = "payment.refunded"
    EXPIRED = "payment.expired"


class WebhookStatus(StrEnum):
    """Producer delivery state."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    EXHAUSTED = "EXHAUSTED"


class DeliveryFault(StrEnum):
    """Deterministic delivery failures available only in test mode."""

    BEFORE_DELIVERY = "before_delivery"
    ACK_LOST_AFTER_CONSUMER = "ack_lost_after_consumer"


class ConsumerFault(StrEnum):
    """Deterministic consumer failure available only in test mode."""

    AFTER_INBOX = "after_inbox"


class ConsumerDisposition(StrEnum):
    """How a verified event affected the merchant projection."""

    APPLIED = "APPLIED"
    STALE = "STALE"
    REDUNDANT = "REDUNDANT"
    DUPLICATE = "DUPLICATE"


class WebhookEventNotFoundError(LookupError):
    """Requested webhook event does not exist."""


class WebhookDeliveryNotReadyError(RuntimeError):
    """Event is delivered, exhausted, leased, or waiting for its retry time."""


class InvalidWebhookSignatureError(ValueError):
    """Webhook signature is missing, malformed, expired, or incorrect."""


class InvalidWebhookPayloadError(ValueError):
    """Verified webhook body does not match the public event contract."""


class WebhookEventCollisionError(RuntimeError):
    """An event ID was repeated with different content."""


class WebhookVersionConflictError(RuntimeError):
    """Two events claim the same payment version with different content."""


class ConcurrentWebhookConsumerError(RuntimeError):
    """Another event changed the consumer projection during processing."""


class MerchantProjectionNotFoundError(LookupError):
    """Requested merchant payment projection does not exist."""


class SimulatedConsumerPersistenceError(RuntimeError):
    """Consumer transaction failed after staging its inbox record."""


@dataclass(frozen=True, slots=True)
class WebhookPaymentSnapshot:
    """Validated payment snapshot carried by a webhook event."""

    id: str
    merchant_reference: str
    amount: int
    currency: str
    status: str
    payment_flow: str
    payment_reference: str | None
    expires_at: datetime | None
    decline_reason: str | None
    authorized_amount: int
    captured_amount: int
    refunded_amount: int
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WebhookEnvelope:
    """Validated webhook envelope and its full payment snapshot."""

    id: str
    event_type: WebhookEventType
    aggregate_version: int
    created_at: datetime
    payment: WebhookPaymentSnapshot


@dataclass(frozen=True, slots=True)
class ConsumerOutcome:
    """Observable consumer result for one received event."""

    event_id: str
    disposition: ConsumerDisposition
    duplicate: bool
    version_gap: bool


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Producer result after one delivery attempt."""

    event_id: str
    attempt_number: int
    outcome: str
    status: WebhookStatus
    response_status: int | None
    next_attempt_at: datetime | None


WebhookReceiver = Callable[[bytes, str, datetime], int]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_datetime(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _payment_payload(payment: PaymentRecord) -> dict[str, Any]:
    return {
        "amount": payment.amount,
        "authorized_amount": payment.authorized_amount,
        "captured_amount": payment.captured_amount,
        "created_at": _format_datetime(payment.created_at),
        "currency": payment.currency,
        "decline_reason": payment.decline_reason,
        "id": payment.id,
        "merchant_reference": payment.merchant_reference,
        "payment_flow": payment.payment_flow,
        "payment_reference": payment.payment_reference,
        "refunded_amount": payment.refunded_amount,
        "status": payment.status,
        "expires_at": (
            _format_datetime(payment.expires_at)
            if payment.expires_at is not None
            else None
        ),
        "updated_at": _format_datetime(payment.updated_at),
        "version": payment.version,
    }


def create_outbox_event(
    session: Session,
    *,
    payment: PaymentRecord,
    event_type: WebhookEventType,
) -> WebhookEventRecord:
    """Stage one full-snapshot event in the payment transaction."""
    event_id = f"evt_{uuid4().hex}"
    created_at = _as_utc(payment.updated_at)
    payload = _canonical_json(
        {
            "aggregate_version": payment.version,
            "created_at": _format_datetime(created_at),
            "id": event_id,
            "payment": _payment_payload(payment),
            "type": event_type.value,
        }
    )
    event = WebhookEventRecord(
        id=event_id,
        payment_id=payment.id,
        event_type=event_type.value,
        aggregate_version=payment.version,
        payload=payload,
        status=WebhookStatus.PENDING.value,
        attempt_count=0,
        next_attempt_at=created_at,
        lease_token=None,
        lease_expires_at=None,
        created_at=created_at,
        delivered_at=None,
    )
    session.add(event)
    return event


def sign_webhook(payload: bytes, *, secret: str, timestamp: int) -> str:
    """Create the public timestamped HMAC-SHA256 signature header."""
    if not secret:
        raise ValueError("Webhook signing secret must not be empty")
    signed = str(timestamp).encode() + b"." + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_webhook_signature(
    payload: bytes,
    *,
    signature_header: str,
    secret: str,
    now: datetime,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
) -> None:
    """Reject malformed, expired, future, or incorrect webhook signatures."""
    try:
        parts = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = int(parts["t"])
        supplied = parts["v1"]
    except (KeyError, ValueError) as error:
        raise InvalidWebhookSignatureError("Malformed webhook signature") from error

    if len(supplied) != 64:
        raise InvalidWebhookSignatureError("Malformed webhook signature")
    current_timestamp = int(_as_utc(now).timestamp())
    if abs(current_timestamp - timestamp) > tolerance_seconds:
        raise InvalidWebhookSignatureError(
            "Webhook signature timestamp is outside tolerance"
        )

    expected = sign_webhook(payload, secret=secret, timestamp=timestamp).split("=", 2)[
        2
    ]
    if not hmac.compare_digest(expected, supplied):
        raise InvalidWebhookSignatureError("Webhook signature does not match")


def _required_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidWebhookPayloadError(f"{name} must be an object")
    return value


def _required_string(values: dict[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value:
        raise InvalidWebhookPayloadError(f"{name} must be a non-empty string")
    return value


def _required_integer(values: dict[str, Any], name: str) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidWebhookPayloadError(f"{name} must be an integer")
    return value


def _required_datetime(values: dict[str, Any], name: str) -> datetime:
    value = _required_string(values, name)
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as error:
        raise InvalidWebhookPayloadError(f"{name} must be an ISO 8601 time") from error


def _optional_string(values: dict[str, Any], name: str) -> str | None:
    value = values.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise InvalidWebhookPayloadError(f"{name} must be a non-empty string or null")
    return value


def _optional_datetime(values: dict[str, Any], name: str) -> datetime | None:
    value = values.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise InvalidWebhookPayloadError(f"{name} must be an ISO 8601 time or null")
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as error:
        raise InvalidWebhookPayloadError(
            f"{name} must be an ISO 8601 time or null"
        ) from error


def _decline_reason(values: dict[str, Any]) -> DeclineReason | None:
    if "decline_reason" not in values:
        raise InvalidWebhookPayloadError("decline_reason is required")
    value = values["decline_reason"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidWebhookPayloadError("decline_reason must be a string or null")
    try:
        return DeclineReason(value)
    except ValueError as error:
        raise InvalidWebhookPayloadError("decline_reason is unsupported") from error


def parse_webhook_payload(payload: bytes) -> WebhookEnvelope:
    """Validate the signed JSON body and financial snapshot invariants."""
    try:
        values = _required_mapping(json.loads(payload), "webhook")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidWebhookPayloadError("Webhook body must be valid JSON") from error

    event_id = _required_string(values, "id")
    event_type_value = _required_string(values, "type")
    try:
        event_type = WebhookEventType(event_type_value)
    except ValueError as error:
        raise InvalidWebhookPayloadError("Webhook event type is unsupported") from error
    aggregate_version = _required_integer(values, "aggregate_version")
    created_at = _required_datetime(values, "created_at")
    payment_values = _required_mapping(values.get("payment"), "payment")

    payment_id = _required_string(payment_values, "id")
    amount = _required_integer(payment_values, "amount")
    authorized_amount = _required_integer(payment_values, "authorized_amount")
    captured_amount = _required_integer(payment_values, "captured_amount")
    refunded_amount = _required_integer(payment_values, "refunded_amount")
    version = _required_integer(payment_values, "version")
    currency_value = _required_string(payment_values, "currency")
    status_value = _required_string(payment_values, "status")
    payment_flow_value = payment_values.get(
        "payment_flow", PaymentFlow.SYNCHRONOUS.value
    )
    if not isinstance(payment_flow_value, str):
        raise InvalidWebhookPayloadError("payment_flow must be a string")
    payment_reference = _optional_string(payment_values, "payment_reference")
    expires_at = _optional_datetime(payment_values, "expires_at")
    decline_reason = _decline_reason(payment_values)

    if amount <= 0 or authorized_amount > amount:
        raise InvalidWebhookPayloadError("Payment amounts are inconsistent")
    if aggregate_version < 1 or version != aggregate_version:
        raise InvalidWebhookPayloadError("Payment version does not match the event")
    try:
        Currency(currency_value)
        status = PaymentStatus(status_value)
        payment_flow = PaymentFlow(payment_flow_value)
        if (status is PaymentStatus.DECLINED) != (decline_reason is not None):
            raise ValueError("Decline reason does not match payment status")
        if payment_flow is PaymentFlow.SYNCHRONOUS:
            if payment_reference is not None or expires_at is not None:
                raise ValueError("Synchronous payment has delayed-flow metadata")
        elif payment_reference is None or expires_at is None:
            raise ValueError("Asynchronous payment metadata is incomplete")
        if status is PaymentStatus.AWAITING_PAYMENT and (
            payment_flow is not PaymentFlow.ASYNCHRONOUS_CONFIRMATION
            or authorized_amount != 0
            or captured_amount != 0
            or refunded_amount != 0
        ):
            raise ValueError("Awaiting payment snapshot is inconsistent")
        if (
            event_type is WebhookEventType.CONFIRMATION_REQUESTED
            and status is not PaymentStatus.AWAITING_PAYMENT
        ):
            raise ValueError("Confirmation request event has the wrong state")
        PaymentState(
            status=status,
            authorized_amount=authorized_amount,
            captured_amount=captured_amount,
            refunded_amount=refunded_amount,
        )
    except ValueError as error:
        raise InvalidWebhookPayloadError("Payment snapshot is invalid") from error

    return WebhookEnvelope(
        id=event_id,
        event_type=event_type,
        aggregate_version=aggregate_version,
        created_at=created_at,
        payment=WebhookPaymentSnapshot(
            id=payment_id,
            merchant_reference=_required_string(payment_values, "merchant_reference"),
            amount=amount,
            currency=currency_value,
            status=status_value,
            payment_flow=payment_flow_value,
            payment_reference=payment_reference,
            expires_at=expires_at,
            decline_reason=(
                decline_reason.value if decline_reason is not None else None
            ),
            authorized_amount=authorized_amount,
            captured_amount=captured_amount,
            refunded_amount=refunded_amount,
            version=version,
            created_at=_required_datetime(payment_values, "created_at"),
            updated_at=_required_datetime(payment_values, "updated_at"),
        ),
    )


def _projection_matches(
    projection: MerchantPaymentProjectionRecord,
    payment: WebhookPaymentSnapshot,
) -> bool:
    expiry_matches = (projection.expires_at is None and payment.expires_at is None) or (
        projection.expires_at is not None
        and payment.expires_at is not None
        and _as_utc(projection.expires_at) == _as_utc(payment.expires_at)
    )
    return (
        projection.merchant_reference == payment.merchant_reference
        and projection.amount == payment.amount
        and projection.currency == payment.currency
        and projection.status == payment.status
        and projection.payment_flow == payment.payment_flow
        and projection.payment_reference == payment.payment_reference
        and expiry_matches
        and projection.decline_reason == payment.decline_reason
        and projection.authorized_amount == payment.authorized_amount
        and projection.captured_amount == payment.captured_amount
        and projection.refunded_amount == payment.refunded_amount
        and projection.aggregate_version == payment.version
    )


def _apply_projection(
    projection: MerchantPaymentProjectionRecord,
    *,
    event_id: str,
    payment: WebhookPaymentSnapshot,
) -> None:
    projection.merchant_reference = payment.merchant_reference
    projection.amount = payment.amount
    projection.currency = payment.currency
    projection.status = payment.status
    projection.payment_flow = payment.payment_flow
    projection.payment_reference = payment.payment_reference
    projection.expires_at = payment.expires_at
    projection.decline_reason = payment.decline_reason
    projection.authorized_amount = payment.authorized_amount
    projection.captured_amount = payment.captured_amount
    projection.refunded_amount = payment.refunded_amount
    projection.aggregate_version = payment.version
    projection.last_event_id = event_id
    projection.updated_at = payment.updated_at


def consume_webhook(
    session: Session,
    *,
    payload: bytes,
    signature_header: str,
    secret: str,
    now: datetime,
    fail_after_inbox: bool = False,
) -> ConsumerOutcome:
    """Verify and apply an event once through one consumer transaction."""
    verify_webhook_signature(
        payload,
        signature_header=signature_header,
        secret=secret,
        now=now,
    )
    envelope = parse_webhook_payload(payload)
    payload_hash = hashlib.sha256(payload).hexdigest()
    existing = session.get(ProcessedWebhookRecord, envelope.id)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise WebhookEventCollisionError(envelope.id)
        return ConsumerOutcome(
            event_id=envelope.id,
            disposition=ConsumerDisposition.DUPLICATE,
            duplicate=True,
            version_gap=existing.version_gap,
        )

    projection = session.get(MerchantPaymentProjectionRecord, envelope.payment.id)
    version_gap = False
    if projection is None:
        version_gap = envelope.aggregate_version > 1
        projection = MerchantPaymentProjectionRecord(
            payment_id=envelope.payment.id,
            merchant_reference=envelope.payment.merchant_reference,
            amount=envelope.payment.amount,
            currency=envelope.payment.currency,
            status=envelope.payment.status,
            payment_flow=envelope.payment.payment_flow,
            payment_reference=envelope.payment.payment_reference,
            expires_at=envelope.payment.expires_at,
            decline_reason=envelope.payment.decline_reason,
            authorized_amount=envelope.payment.authorized_amount,
            captured_amount=envelope.payment.captured_amount,
            refunded_amount=envelope.payment.refunded_amount,
            aggregate_version=envelope.payment.version,
            last_event_id=envelope.id,
            updated_at=envelope.payment.updated_at,
        )
        session.add(projection)
        disposition = ConsumerDisposition.APPLIED
    elif envelope.aggregate_version > projection.aggregate_version:
        version_gap = envelope.aggregate_version > projection.aggregate_version + 1
        _apply_projection(projection, event_id=envelope.id, payment=envelope.payment)
        disposition = ConsumerDisposition.APPLIED
    elif envelope.aggregate_version < projection.aggregate_version:
        disposition = ConsumerDisposition.STALE
    elif _projection_matches(projection, envelope.payment):
        disposition = ConsumerDisposition.REDUNDANT
    else:
        raise WebhookVersionConflictError(envelope.payment.id)

    inbox = ProcessedWebhookRecord(
        event_id=envelope.id,
        payment_id=envelope.payment.id,
        event_type=envelope.event_type.value,
        aggregate_version=envelope.aggregate_version,
        payload_hash=payload_hash,
        disposition=disposition.value,
        version_gap=version_gap,
        processed_at=_as_utc(now),
    )
    session.add(inbox)
    try:
        session.flush()
        if fail_after_inbox:
            raise SimulatedConsumerPersistenceError
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.get(ProcessedWebhookRecord, envelope.id)
        if existing is None:
            raise ConcurrentWebhookConsumerError(envelope.payment.id) from None
        if existing.payload_hash != payload_hash:
            raise WebhookEventCollisionError(envelope.id) from None
        return ConsumerOutcome(
            event_id=envelope.id,
            disposition=ConsumerDisposition.DUPLICATE,
            duplicate=True,
            version_gap=existing.version_gap,
        )
    except Exception:
        session.rollback()
        raise

    return ConsumerOutcome(
        event_id=envelope.id,
        disposition=disposition,
        duplicate=False,
        version_gap=version_gap,
    )


def _claim_delivery(
    session: Session,
    *,
    event_id: str,
    now: datetime,
) -> str:
    event = session.get(WebhookEventRecord, event_id)
    if event is None:
        raise WebhookEventNotFoundError(event_id)

    lease_token = f"lease_{uuid4().hex}"
    current = _as_utc(now)
    statement = (
        update(WebhookEventRecord)
        .where(
            WebhookEventRecord.id == event_id,
            or_(
                (
                    (WebhookEventRecord.status == WebhookStatus.PENDING.value)
                    & (WebhookEventRecord.next_attempt_at <= current)
                ),
                (
                    (WebhookEventRecord.status == WebhookStatus.PROCESSING.value)
                    & (WebhookEventRecord.lease_expires_at <= current)
                ),
            ),
        )
        .values(
            status=WebhookStatus.PROCESSING.value,
            lease_token=lease_token,
            lease_expires_at=current + timedelta(seconds=DELIVERY_LEASE_SECONDS),
        )
        .execution_options(synchronize_session=False)
    )
    result = session.execute(statement)
    session.commit()
    if result.rowcount != 1:
        raise WebhookDeliveryNotReadyError(event_id)
    session.expire_all()
    return lease_token


def _finalize_delivery(
    session: Session,
    *,
    event_id: str,
    lease_token: str,
    now: datetime,
    outcome: str,
    response_status: int | None,
    error_code: str | None,
) -> DeliveryResult:
    event = session.get(WebhookEventRecord, event_id)
    if event is None:
        raise WebhookEventNotFoundError(event_id)
    if event.lease_token != lease_token:
        raise WebhookDeliveryNotReadyError(event_id)

    attempt_number = event.attempt_count + 1
    event.attempt_count = attempt_number
    event.lease_token = None
    event.lease_expires_at = None
    current = _as_utc(now)
    succeeded = response_status is not None and 200 <= response_status < 300
    if succeeded:
        event.status = WebhookStatus.DELIVERED.value
        event.delivered_at = current
        event.next_attempt_at = current
        next_attempt_at = None
    elif attempt_number >= MAX_DELIVERY_ATTEMPTS:
        event.status = WebhookStatus.EXHAUSTED.value
        event.next_attempt_at = current
        next_attempt_at = None
    else:
        delay = RETRY_DELAYS_SECONDS[attempt_number - 1]
        next_attempt_at = current + timedelta(seconds=delay)
        event.status = WebhookStatus.PENDING.value
        event.next_attempt_at = next_attempt_at

    session.add(
        WebhookDeliveryAttemptRecord(
            id=f"att_{uuid4().hex}",
            event_id=event.id,
            attempt_number=attempt_number,
            outcome=outcome,
            response_status=response_status,
            error_code=error_code,
            attempted_at=current,
        )
    )
    session.commit()
    return DeliveryResult(
        event_id=event.id,
        attempt_number=attempt_number,
        outcome=outcome,
        status=WebhookStatus(event.status),
        response_status=response_status,
        next_attempt_at=next_attempt_at,
    )


def dispatch_webhook(
    session: Session,
    *,
    event_id: str,
    secret: str,
    receiver: WebhookReceiver,
    now: datetime,
    fault: DeliveryFault | None = None,
) -> DeliveryResult:
    """Lease, sign, deliver, and record one at-least-once attempt."""
    lease_token = _claim_delivery(session, event_id=event_id, now=now)
    event = session.get(WebhookEventRecord, event_id)
    if event is None:  # pragma: no cover - protected by the delivery lease
        raise WebhookEventNotFoundError(event_id)
    payload = event.payload.encode()
    signature = sign_webhook(
        payload, secret=secret, timestamp=int(_as_utc(now).timestamp())
    )

    response_status: int | None = None
    error_code: str | None = None
    outcome = "SUCCESS"
    try:
        if fault is DeliveryFault.BEFORE_DELIVERY:
            raise TimeoutError("simulated timeout before consumer")
        response_status = receiver(payload, signature, _as_utc(now))
        if fault is DeliveryFault.ACK_LOST_AFTER_CONSUMER:
            response_status = None
            raise TimeoutError("simulated acknowledgement loss")
        if not 200 <= response_status < 300:
            outcome = "HTTP_ERROR"
            error_code = f"http_{response_status}"
    except TimeoutError:
        outcome = "TIMEOUT"
        response_status = None
        error_code = "delivery_timeout"
    except ConnectionError:
        outcome = "CONNECTION_ERROR"
        response_status = None
        error_code = "connection_error"

    return _finalize_delivery(
        session,
        event_id=event_id,
        lease_token=lease_token,
        now=now,
        outcome=outcome,
        response_status=response_status,
        error_code=error_code,
    )


def get_webhook_events(session: Session) -> list[WebhookEventRecord]:
    """Return outbox events in deterministic creation order."""
    statement = select(WebhookEventRecord).order_by(
        WebhookEventRecord.created_at,
        WebhookEventRecord.id,
    )
    return list(session.scalars(statement))


def get_delivery_attempts(
    session: Session,
    event_id: str,
) -> list[WebhookDeliveryAttemptRecord]:
    """Return one event's delivery history."""
    if session.get(WebhookEventRecord, event_id) is None:
        raise WebhookEventNotFoundError(event_id)
    statement = (
        select(WebhookDeliveryAttemptRecord)
        .where(WebhookDeliveryAttemptRecord.event_id == event_id)
        .order_by(WebhookDeliveryAttemptRecord.attempt_number)
    )
    return list(session.scalars(statement))


def get_merchant_projection(
    session: Session,
    payment_id: str,
) -> MerchantPaymentProjectionRecord | None:
    """Return the consumer view without reading the source payment table."""
    return session.get(MerchantPaymentProjectionRecord, payment_id)


def require_merchant_projection(
    session: Session,
    payment_id: str,
) -> MerchantPaymentProjectionRecord:
    """Return a merchant projection or raise a public not-found error."""
    projection = get_merchant_projection(session, payment_id)
    if projection is None:
        raise MerchantProjectionNotFoundError(payment_id)
    return projection
