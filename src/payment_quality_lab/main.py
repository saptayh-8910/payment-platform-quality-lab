"""FastAPI application factory and local entry point."""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from payment_quality_lab.api.routes import get_session, router
from payment_quality_lab.domain.payment import (
    InvalidPaymentTransitionError,
    RefundAmountExceededError,
)
from payment_quality_lab.persistence.database import (
    Base,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from payment_quality_lab.persistence.migrations import require_current_schema
from payment_quality_lab.services.payments import (
    ConcurrentPaymentUpdateError,
    FailureInjectionDisabledError,
    IdempotencyConflictError,
    PaymentNotFoundError,
    SimulatedPaymentTimeoutError,
)
from payment_quality_lab.services.reconciliation import (
    SettlementBatchNotFoundError,
    SettlementPaymentNotFoundError,
    SettlementPaymentOutsideCutoffError,
)
from payment_quality_lab.services.webhooks import (
    ConcurrentWebhookConsumerError,
    InvalidWebhookPayloadError,
    InvalidWebhookSignatureError,
    MerchantProjectionNotFoundError,
    SimulatedConsumerPersistenceError,
    WebhookDeliveryNotReadyError,
    WebhookEventCollisionError,
    WebhookEventNotFoundError,
    WebhookVersionConflictError,
)

DEFAULT_WEBHOOK_SIGNING_SECRET = "whsec_local_synthetic_only"
CHECKOUT_DIRECTORY = Path(__file__).parent / "web" / "checkout"


def create_app(
    database_url: str | None = None,
    *,
    enable_failure_injection: bool = False,
    webhook_signing_secret: str = DEFAULT_WEBHOOK_SIGNING_SECRET,
    initialize_schema: bool = False,
    payment_clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Construct an application, optionally creating an isolated test schema."""
    resolved_url = database_url or os.getenv(
        "PAYMENT_LAB_DATABASE_URL", "sqlite:///payment_lab.db"
    )
    engine = create_database_engine(resolved_url)
    session_factory = create_session_factory(engine)
    if initialize_schema:
        Base.metadata.create_all(engine)
    else:
        try:
            require_current_schema(engine)
        except Exception:
            engine.dispose()
            raise

    app = FastAPI(
        title="Payment Platform Quality Lab",
        version="0.6.0",
        description="Privacy-safe payment lifecycle simulator",
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.failure_injection_enabled = enable_failure_injection
    app.state.webhook_signing_secret = webhook_signing_secret
    app.state.payment_clock = payment_clock or (lambda: datetime.now(UTC))

    def provide_session() -> Iterator[Session]:
        yield from session_scope(session_factory)

    app.dependency_overrides[get_session] = provide_session
    app.include_router(router)
    app.mount(
        "/checkout/assets",
        StaticFiles(directory=CHECKOUT_DIRECTORY),
        name="checkout-assets",
    )

    @app.get("/checkout", include_in_schema=False)
    def checkout() -> FileResponse:
        """Serve the privacy-safe multilingual test checkout."""
        return FileResponse(
            CHECKOUT_DIRECTORY / "index.html",
            media_type="text/html; charset=utf-8",
        )

    @app.exception_handler(PaymentNotFoundError)
    async def payment_not_found(
        _request: Request, error: PaymentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "payment_not_found",
                "message": f"Payment {error.args[0]} was not found",
            },
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict(
        _request: Request, _error: IdempotencyConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "idempotency_conflict",
                "message": "Idempotency key was already used for another request",
            },
        )

    @app.exception_handler(ConcurrentPaymentUpdateError)
    async def concurrent_payment_update(
        _request: Request, _error: ConcurrentPaymentUpdateError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "concurrent_payment_update",
                "message": "Payment changed concurrently; retrieve it before retrying",
            },
        )

    @app.exception_handler(FailureInjectionDisabledError)
    async def failure_injection_disabled(
        _request: Request, _error: FailureInjectionDisabledError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "code": "failure_injection_disabled",
                "message": "Test failure controls are disabled",
            },
        )

    @app.exception_handler(SimulatedPaymentTimeoutError)
    async def simulated_payment_timeout(
        _request: Request, _error: SimulatedPaymentTimeoutError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "code": "payment_timeout",
                "message": (
                    "Payment outcome is uncertain; retry with the same idempotency key"
                ),
            },
        )

    @app.exception_handler(InvalidWebhookSignatureError)
    async def invalid_webhook_signature(
        _request: Request, error: InvalidWebhookSignatureError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "code": "invalid_webhook_signature",
                "message": str(error),
            },
        )

    @app.exception_handler(InvalidWebhookPayloadError)
    async def invalid_webhook_payload(
        _request: Request, error: InvalidWebhookPayloadError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "invalid_webhook_payload",
                "message": str(error),
            },
        )

    @app.exception_handler(WebhookEventCollisionError)
    async def webhook_event_collision(
        _request: Request, _error: WebhookEventCollisionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "webhook_event_collision",
                "message": "Webhook event ID was reused with different content",
            },
        )

    @app.exception_handler(WebhookVersionConflictError)
    async def webhook_version_conflict(
        _request: Request, _error: WebhookVersionConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "webhook_version_conflict",
                "message": "Payment version conflicts with the merchant projection",
            },
        )

    @app.exception_handler(ConcurrentWebhookConsumerError)
    async def concurrent_webhook_consumer(
        _request: Request, _error: ConcurrentWebhookConsumerError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "concurrent_webhook_consumer",
                "message": "Merchant projection changed concurrently; retry the event",
            },
        )

    @app.exception_handler(WebhookDeliveryNotReadyError)
    async def webhook_delivery_not_ready(
        _request: Request, _error: WebhookDeliveryNotReadyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "webhook_delivery_not_ready",
                "message": "Webhook event is not ready for a delivery attempt",
            },
        )

    @app.exception_handler(WebhookEventNotFoundError)
    async def webhook_event_not_found(
        _request: Request, error: WebhookEventNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "webhook_event_not_found",
                "message": f"Webhook event {error.args[0]} was not found",
            },
        )

    @app.exception_handler(MerchantProjectionNotFoundError)
    async def merchant_projection_not_found(
        _request: Request, error: MerchantProjectionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "merchant_projection_not_found",
                "message": f"Merchant projection {error.args[0]} was not found",
            },
        )

    @app.exception_handler(SimulatedConsumerPersistenceError)
    async def simulated_consumer_failure(
        _request: Request, _error: SimulatedConsumerPersistenceError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": "simulated_consumer_failure",
                "message": "Consumer transaction failed before commit",
            },
        )

    @app.exception_handler(SettlementBatchNotFoundError)
    async def settlement_batch_not_found(
        _request: Request, error: SettlementBatchNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "settlement_batch_not_found",
                "message": f"Settlement batch {error.args[0]} was not found",
            },
        )

    @app.exception_handler(SettlementPaymentNotFoundError)
    async def settlement_payment_not_found(
        _request: Request, error: SettlementPaymentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "settlement_payment_not_found",
                "message": f"Settlement payment {error.args[0]} was not found",
            },
        )

    @app.exception_handler(SettlementPaymentOutsideCutoffError)
    async def settlement_payment_outside_cutoff(
        _request: Request, error: SettlementPaymentOutsideCutoffError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "settlement_payment_outside_cutoff",
                "message": (
                    f"Settlement payment {error.args[0]} was created after the cutoff"
                ),
            },
        )

    @app.exception_handler(InvalidPaymentTransitionError)
    async def invalid_payment_transition(
        _request: Request, error: InvalidPaymentTransitionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "invalid_payment_transition",
                "message": str(error),
            },
        )

    @app.exception_handler(RefundAmountExceededError)
    async def refund_amount_exceeded(
        _request: Request, error: RefundAmountExceededError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "refund_amount_exceeded",
                "message": str(error),
                "requested_amount": error.requested,
                "refundable_amount": error.available,
            },
        )

    return app


def create_runtime_app() -> FastAPI:
    """Construct the local service only after its schema has been migrated."""
    return create_app(initialize_schema=False)


def run() -> None:
    """Run the local development server."""
    uvicorn.run(create_runtime_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
