# Payment Platform Quality Lab

Payment Platform Quality Lab is a privacy-safe payment simulator and QA
portfolio project. It demonstrates risk-based testing of payment lifecycles,
failure recovery, financial correctness, and platform reliability without
processing real payments or cardholder data.

## Project goals

- Model authorization, capture, cancellation, decline, and refund behavior.
- Prevent duplicate financial effects through idempotency controls.
- Exercise signed webhooks, duplicate delivery, retries, and out-of-order events.
- Verify monetary precision for USD and zero-decimal JPY transactions.
- Reconcile API state, immutable ledger entries, webhook history, and settlement
  records.
- Combine unit, API, integration, browser, exploratory, regression, and
  performance testing.
- Demonstrate release-quality evidence through CI reports and explicit gates.

## Non-goals

- Processing real payments or integrating with a production payment processor.
- Accepting, storing, or transmitting cardholder data.
- Claiming production-grade PCI DSS, security, or regulatory compliance.
- Building a feature-complete ecommerce application.
- Reproducing a specific payment provider's proprietary implementation.

## Planned system

The system under test will be a small Python payment service with a minimal
English/Japanese checkout. The service will use integer minor units, an explicit
payment state machine, an immutable ledger, idempotent write operations, signed
webhook events, deterministic failure injection, and reconciliation tooling.

Planned test tooling:

- pytest for domain, API, and integration testing
- FastAPI TestClient for service-level API checks
- Playwright for English/Japanese browser journeys
- Hypothesis for financial and state-machine invariants
- Locust for a small reliability and performance baseline
- Ruff and branch-aware coverage for fast feedback
- GitHub Actions for pull-request and release quality gates

## Delivery milestones

1. Project foundation, requirements, and risk-based test plan
2. Authorization vertical slice with persistence and CI
3. Payment lifecycle and financial invariants
4. Idempotency, ledger correctness, concurrency, and failure injection
5. Webhook delivery, consumption, and reconciliation
6. English/Japanese checkout with Playwright
7. Manual testing, exploratory sessions, and defect evidence
8. Performance baseline and portfolio-ready reporting

## Current status

The first vertical slice implements deterministic payment authorization and
decline behavior through a FastAPI service. Approved payments create one
financial ledger entry, declined payments create none, and equivalent requests
can safely replay their original result using an idempotency key.

Current automated evidence includes pure domain tests, HTTP contract tests,
SQLite integration tests, branch-aware coverage, linting, formatting, and a
Python 3.12/3.14 GitHub Actions matrix.

## Quick start

Python 3.12 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev]'
python -m pytest
```

Start the service:

```bash
payment-quality-lab
```

The API documentation is then available at
<http://127.0.0.1:8000/docs>.

Create a synthetic JPY authorization:

```bash
curl --request POST http://127.0.0.1:8000/payments \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: demo-order-0001' \
  --data '{
    "merchant_reference": "order-2026-0001",
    "amount": 2500,
    "currency": "JPY",
    "payment_method_token": "tok_approved"
  }'
```

Only deterministic synthetic tokens are accepted:

- `tok_approved` creates an authorized payment and authorization ledger entry.
- `tok_declined` creates a declined payment without a financial ledger effect.

These are simulator controls, not real payment credentials.

See:

- [Payment requirements](docs/payment-requirements.md)
- [Risk-based test plan](docs/test-plan.md)
- [Defect reports](docs/defects/)

## License

This project is available under the [MIT License](LICENSE).
