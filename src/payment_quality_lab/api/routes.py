"""Payment HTTP endpoints."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from payment_quality_lab.api.schemas import (
    AuthorizePaymentRequest,
    LedgerEntryResponse,
    MerchantProjectionResponse,
    PaymentResponse,
    ReconciliationReportResponse,
    ReconciliationRequest,
    RefundPaymentRequest,
    SettlementBatchCreateRequest,
    SettlementBatchResponse,
    WebhookConsumerResponse,
    WebhookDeliveryAttemptResponse,
    WebhookDeliveryResponse,
    WebhookEventResponse,
)
from payment_quality_lab.persistence.models import SettlementBatchRecord
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    FailureInjectionDisabledError,
    FailurePoint,
    LifecycleOutcome,
    authorize_payment,
    cancel_payment,
    capture_payment,
    get_ledger_entries,
    get_payment,
    refund_payment,
)
from payment_quality_lab.services.reconciliation import (
    SettlementInput,
    create_settlement_batch,
    get_settlement_records,
    reconcile_settlement_batch,
)
from payment_quality_lab.services.webhooks import (
    ConsumerFault,
    DeliveryFault,
    consume_webhook,
    dispatch_webhook,
    get_delivery_attempts,
    get_webhook_events,
    require_merchant_projection,
)

router = APIRouter()


def get_session() -> Session:  # pragma: no cover - replaced by app dependency
    """Dependency marker replaced during application construction."""
    raise RuntimeError("Database dependency is not configured")


def get_payment_clock(request: Request) -> Callable[[], datetime]:
    """Return the application clock used by payment-creation transactions."""
    return request.app.state.payment_clock


SessionDependency = Annotated[Session, Depends(get_session)]
PaymentClockDependency = Annotated[Callable[[], datetime], Depends(get_payment_clock)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]
FailurePointHeader = Annotated[
    FailurePoint | None,
    Header(alias="X-Payment-Lab-Failure"),
]
DeliveryFaultHeader = Annotated[
    DeliveryFault | None,
    Header(alias="X-Payment-Lab-Delivery-Failure"),
]
ConsumerFaultHeader = Annotated[
    ConsumerFault | None,
    Header(alias="X-Payment-Lab-Consumer-Failure"),
]
WebhookSignature = Annotated[
    str,
    Header(alias="Webhook-Signature", min_length=1),
]


def resolve_failure_point(
    request: Request,
    failure_point: FailurePointHeader = None,
) -> FailurePoint | None:
    """Expose deterministic failures only in an explicitly enabled app."""
    if failure_point is not None and not request.app.state.failure_injection_enabled:
        raise FailureInjectionDisabledError
    return failure_point


FailurePointDependency = Annotated[FailurePoint | None, Depends(resolve_failure_point)]


def resolve_delivery_fault(
    request: Request,
    fault: DeliveryFaultHeader = None,
) -> DeliveryFault | None:
    """Allow deterministic delivery failures only in explicit test mode."""
    if fault is not None and not request.app.state.failure_injection_enabled:
        raise FailureInjectionDisabledError
    return fault


def resolve_consumer_fault(
    request: Request,
    fault: ConsumerFaultHeader = None,
) -> ConsumerFault | None:
    """Allow deterministic consumer failures only in explicit test mode."""
    if fault is not None and not request.app.state.failure_injection_enabled:
        raise FailureInjectionDisabledError
    return fault


DeliveryFaultDependency = Annotated[
    DeliveryFault | None, Depends(resolve_delivery_fault)
]
ConsumerFaultDependency = Annotated[
    ConsumerFault | None, Depends(resolve_consumer_fault)
]


@router.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Return a lightweight process health signal."""
    return {"status": "ok"}


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
)
def create_payment(
    payload: AuthorizePaymentRequest,
    idempotency_key: IdempotencyKey,
    session: SessionDependency,
    response: Response,
    failure_point: FailurePointDependency,
    clock: PaymentClockDependency,
) -> PaymentResponse:
    """Authorize or decline a payment using deterministic synthetic tokens."""
    outcome = authorize_payment(
        session,
        command=AuthorizationCommand(
            merchant_reference=payload.merchant_reference,
            amount=payload.amount,
            currency=payload.currency,
            payment_method_token=payload.payment_method_token,
        ),
        idempotency_key=idempotency_key,
        failure_point=failure_point,
        clock=clock,
    )
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return PaymentResponse.from_record(outcome.payment)


def _lifecycle_response(
    outcome: LifecycleOutcome, response: Response
) -> PaymentResponse:
    """Map lifecycle outcomes and expose idempotent replay metadata."""
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return PaymentResponse.from_record(outcome.payment)


@router.post(
    "/payments/{payment_id}/capture",
    response_model=PaymentResponse,
    tags=["payments"],
)
def capture_authorization(
    payment_id: str,
    idempotency_key: IdempotencyKey,
    session: SessionDependency,
    response: Response,
    failure_point: FailurePointDependency,
) -> PaymentResponse:
    """Capture the full amount of an authorized payment."""
    outcome = capture_payment(
        session,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
        failure_point=failure_point,
    )
    return _lifecycle_response(outcome, response)


@router.post(
    "/payments/{payment_id}/cancel",
    response_model=PaymentResponse,
    tags=["payments"],
)
def cancel_authorization(
    payment_id: str,
    idempotency_key: IdempotencyKey,
    session: SessionDependency,
    response: Response,
    failure_point: FailurePointDependency,
) -> PaymentResponse:
    """Cancel an authorized payment before capture."""
    outcome = cancel_payment(
        session,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
        failure_point=failure_point,
    )
    return _lifecycle_response(outcome, response)


@router.post(
    "/payments/{payment_id}/refund",
    response_model=PaymentResponse,
    tags=["payments"],
)
def refund_capture(
    payment_id: str,
    payload: RefundPaymentRequest,
    idempotency_key: IdempotencyKey,
    session: SessionDependency,
    response: Response,
    failure_point: FailurePointDependency,
) -> PaymentResponse:
    """Apply a partial or full refund to captured funds."""
    outcome = refund_payment(
        session,
        payment_id=payment_id,
        amount=payload.amount,
        idempotency_key=idempotency_key,
        failure_point=failure_point,
    )
    return _lifecycle_response(outcome, response)


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    tags=["payments"],
)
def retrieve_payment(payment_id: str, session: SessionDependency) -> PaymentResponse:
    """Retrieve a payment by its server-generated identifier."""
    return PaymentResponse.from_record(get_payment(session, payment_id))


@router.get(
    "/payments/{payment_id}/ledger",
    response_model=list[LedgerEntryResponse],
    tags=["payments"],
)
def retrieve_ledger(
    payment_id: str, session: SessionDependency
) -> list[LedgerEntryResponse]:
    """Retrieve the financial effects recorded for a payment."""
    return [
        LedgerEntryResponse.from_record(entry)
        for entry in get_ledger_entries(session, payment_id)
    ]


@router.get(
    "/webhooks/events",
    response_model=list[WebhookEventResponse],
    tags=["webhooks"],
)
def retrieve_webhook_events(
    session: SessionDependency,
) -> list[WebhookEventResponse]:
    """List producer outbox events and their delivery state."""
    return [
        WebhookEventResponse.from_record(event) for event in get_webhook_events(session)
    ]


@router.get(
    "/webhooks/events/{event_id}/attempts",
    response_model=list[WebhookDeliveryAttemptResponse],
    tags=["webhooks"],
)
def retrieve_webhook_attempts(
    event_id: str,
    session: SessionDependency,
) -> list[WebhookDeliveryAttemptResponse]:
    """List the deterministic delivery history for one event."""
    return [
        WebhookDeliveryAttemptResponse.from_record(attempt)
        for attempt in get_delivery_attempts(session, event_id)
    ]


@router.post(
    "/webhook-consumer",
    response_model=WebhookConsumerResponse,
    tags=["webhooks"],
)
async def receive_webhook(
    request: Request,
    signature: WebhookSignature,
    session: SessionDependency,
    fault: ConsumerFaultDependency,
) -> WebhookConsumerResponse:
    """Verify and apply a signed event to the merchant projection."""
    outcome = consume_webhook(
        session,
        payload=await request.body(),
        signature_header=signature,
        secret=request.app.state.webhook_signing_secret,
        now=datetime.now(UTC),
        fail_after_inbox=fault is ConsumerFault.AFTER_INBOX,
    )
    return WebhookConsumerResponse.from_outcome(outcome)


@router.post(
    "/webhooks/events/{event_id}/deliver",
    response_model=WebhookDeliveryResponse,
    tags=["webhooks"],
)
def deliver_webhook_event(
    event_id: str,
    request: Request,
    session: SessionDependency,
    fault: DeliveryFaultDependency,
) -> WebhookDeliveryResponse:
    """Run one signed in-process delivery attempt for the simulator."""

    def receiver(payload: bytes, signature: str, received_at: datetime) -> int:
        with request.app.state.session_factory() as consumer_session:
            consume_webhook(
                consumer_session,
                payload=payload,
                signature_header=signature,
                secret=request.app.state.webhook_signing_secret,
                now=received_at,
            )
        return status.HTTP_200_OK

    result = dispatch_webhook(
        session,
        event_id=event_id,
        secret=request.app.state.webhook_signing_secret,
        receiver=receiver,
        now=datetime.now(UTC),
        fault=fault,
    )
    return WebhookDeliveryResponse.from_result(result)


@router.get(
    "/merchant-projections/{payment_id}",
    response_model=MerchantProjectionResponse,
    tags=["webhooks"],
)
def retrieve_merchant_projection(
    payment_id: str,
    session: SessionDependency,
) -> MerchantProjectionResponse:
    """Retrieve the merchant view built only from accepted webhooks."""
    return MerchantProjectionResponse.from_record(
        require_merchant_projection(session, payment_id)
    )


@router.post(
    "/settlement-batches",
    response_model=SettlementBatchResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reconciliation"],
)
def import_settlement_batch(
    payload: SettlementBatchCreateRequest,
    session: SessionDependency,
) -> SettlementBatchResponse:
    """Import synthetic external rows without changing payment state."""
    batch = create_settlement_batch(
        session,
        cutoff=payload.cutoff,
        entries=[
            SettlementInput(
                payment_id=entry.payment_id,
                amount=entry.amount,
                currency=entry.currency,
            )
            for entry in payload.entries
        ],
    )
    return SettlementBatchResponse.from_records(
        batch,
        get_settlement_records(session, batch.id),
    )


@router.get(
    "/settlement-batches/{batch_id}",
    response_model=SettlementBatchResponse,
    tags=["reconciliation"],
)
def retrieve_settlement_batch(
    batch_id: str,
    session: SessionDependency,
) -> SettlementBatchResponse:
    """Retrieve an imported settlement batch for investigation."""
    records = get_settlement_records(session, batch_id)
    batch = session.get(SettlementBatchRecord, batch_id)
    assert batch is not None
    return SettlementBatchResponse.from_records(batch, records)


@router.post(
    "/reconciliation-reports",
    response_model=ReconciliationReportResponse,
    tags=["reconciliation"],
)
def create_reconciliation_report(
    payload: ReconciliationRequest,
    session: SessionDependency,
) -> ReconciliationReportResponse:
    """Compare payment, ledger, webhook, and settlement sources read-only."""
    return ReconciliationReportResponse.from_result(
        reconcile_settlement_batch(
            session,
            batch_id=payload.settlement_batch_id,
        )
    )
