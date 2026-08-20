"""Controlled HTTP server used only by the browser acceptance suite."""

import os

import uvicorn

from payment_quality_lab.main import create_app


def run() -> None:
    database_url = os.environ["PAYMENT_LAB_TEST_DATABASE_URL"]
    port = int(os.environ["PAYMENT_LAB_TEST_PORT"])
    app = create_app(database_url, enable_failure_injection=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run()
