"""Controlled HTTP server used only by the browser acceptance suite."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import uvicorn

from payment_quality_lab.main import create_app


def run() -> None:
    database_url = os.environ["PAYMENT_LAB_TEST_DATABASE_URL"]
    port = int(os.environ["PAYMENT_LAB_TEST_PORT"])
    app = create_app(
        database_url,
        enable_failure_injection=True,
        initialize_schema=True,
    )

    # Test-only setup boundary, never registered in the application package.
    @app.post("/test/payments/{payment_id}/{outcome}")
    def advance(payment_id: str, outcome: str):
        from payment_quality_lab.domain.payment import Currency
        from payment_quality_lab.persistence.models import PaymentRecord
        from payment_quality_lab.services.confirmations import (
            ConfirmationCommand,
            expire_due_payments,
            process_confirmation,
        )
        from payment_quality_lab.services.payments import cancel_payment

        with app.state.session_factory() as session:
            payment = session.get(PaymentRecord, payment_id)
            assert payment is not None
            if outcome == "expired":
                expire_due_payments(session, now=payment.expires_at.replace(tzinfo=UTC))
            elif outcome == "confirmed":
                process_confirmation(
                    session,
                    command=ConfirmationCommand(
                        f"cnf_{uuid4().hex}",
                        payment.payment_reference,
                        payment.amount,
                        Currency(payment.currency),
                    ),
                    clock=lambda: datetime.now(UTC),
                )
            elif outcome == "cancelled":
                cancel_payment(
                    session,
                    payment_id=payment_id,
                    idempotency_key=f"cancel-{uuid4().hex}",
                )
            else:
                raise ValueError("Unsupported test outcome")
        return {"ok": True}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run()
