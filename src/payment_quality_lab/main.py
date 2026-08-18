"""FastAPI application factory and local entry point."""

import os
from collections.abc import Iterator

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
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
from payment_quality_lab.services.payments import (
    ConcurrentPaymentUpdateError,
    FailureInjectionDisabledError,
    IdempotencyConflictError,
    PaymentNotFoundError,
    SimulatedPaymentTimeoutError,
)


def create_app(
    database_url: str | None = None,
    *,
    enable_failure_injection: bool = False,
) -> FastAPI:
    """Construct an isolated application instance."""
    resolved_url = database_url or os.getenv(
        "PAYMENT_LAB_DATABASE_URL", "sqlite:///payment_lab.db"
    )
    engine = create_database_engine(resolved_url)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    app = FastAPI(
        title="Payment Platform Quality Lab",
        version="0.3.0",
        description="Privacy-safe payment lifecycle simulator",
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.failure_injection_enabled = enable_failure_injection

    def provide_session() -> Iterator[Session]:
        yield from session_scope(session_factory)

    app.dependency_overrides[get_session] = provide_session
    app.include_router(router)

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


app = create_app()


def run() -> None:
    """Run the local development server."""
    uvicorn.run("payment_quality_lab.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
