"""Payment HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from payment_quality_lab.api.schemas import (
    AuthorizePaymentRequest,
    LedgerEntryResponse,
    PaymentResponse,
)
from payment_quality_lab.services.payments import (
    AuthorizationCommand,
    authorize_payment,
    get_ledger_entries,
    get_payment,
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
