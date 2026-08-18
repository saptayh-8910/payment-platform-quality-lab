"""Payment HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from payment_quality_lab.api.schemas import (
    AuthorizePaymentRequest,
    LedgerEntryResponse,
    PaymentResponse,
    RefundPaymentRequest,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    LifecycleOutcome,
    authorize_payment,
    cancel_payment,
    capture_payment,
    get_ledger_entries,
    get_payment,
    refund_payment,
)

router = APIRouter()


def get_session() -> Session:  # pragma: no cover - replaced by app dependency
    """Dependency marker replaced during application construction."""
    raise RuntimeError("Database dependency is not configured")


SessionDependency = Annotated[Session, Depends(get_session)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
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
) -> PaymentResponse:
    """Capture the full amount of an authorized payment."""
    outcome = capture_payment(
        session,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
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
) -> PaymentResponse:
    """Cancel an authorized payment before capture."""
    outcome = cancel_payment(
        session,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
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
) -> PaymentResponse:
    """Apply a partial or full refund to captured funds."""
    outcome = refund_payment(
        session,
        payment_id=payment_id,
        amount=payload.amount,
        idempotency_key=idempotency_key,
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
