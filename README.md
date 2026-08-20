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

## System design

The system under test is a small Python payment service with a minimal
English/Japanese checkout. The service uses integer minor units, an explicit
payment state machine, an immutable ledger, idempotency claims with immutable
response snapshots, optimistic concurrency control, a transactional webhook
outbox, and multi-source financial reconciliation.

Test tooling:

- pytest for domain, API, and integration testing
- FastAPI TestClient for service-level API checks
- TypeScript Playwright with Cucumber-JS for selected English/Japanese journeys
- Hypothesis for financial and state-machine invariants
- k6 for the planned reliability and performance baseline
- Ruff and branch-aware coverage for fast feedback
- GitHub Actions for pull-request and release quality gates

## Delivery milestones

1. Project foundation, requirements, and risk-based test plan
2. Authorization vertical slice with persistence and CI
3. Payment lifecycle and financial invariants
4. Idempotency, ledger correctness, concurrency, and failure injection
5. Webhook delivery, consumption, and reconciliation
6. English/Japanese checkout with TypeScript Playwright and Cucumber-JS
7. Service-to-service testing, exploratory sessions, and defect evidence
8. Performance baseline and portfolio-ready reporting

## Current status

The service implements deterministic authorization and decline behavior plus
full capture, pre-capture cancellation, and partial or full refunds. Every
accepted lifecycle operation records one immutable ledger entry, increments the
payment version once, and commits its idempotency record in the same transaction.
Invalid transitions and over-refunds leave payment and ledger state unchanged.

Current automated evidence includes example-based and Hypothesis-generated
domain tests, HTTP contract tests, SQLite integration and constraint tests,
branch-aware coverage, linting, formatting, and a Python 3.12/3.14 GitHub
Actions matrix.

Concurrent equivalent requests now claim one idempotency key before applying a
financial mutation. Successful outcomes store an immutable response snapshot,
so a later retry returns the original result even after the payment changes.
Optimistic version checks reject stale competing transitions, while deterministic
pre-commit and post-commit timeouts demonstrate rollback and safe retry behavior.
Failure controls are disabled unless an application instance explicitly enables
test/demo mode.

Every accepted payment version now creates one full-snapshot webhook event in
the financial transaction. The producer signs deliveries with HMAC-SHA256 and
records deterministic retry attempts. A simulated merchant consumer verifies
the raw body, stores processed event IDs, applies newer versions, and ignores
safe duplicates or stale events.

Synthetic settlement batches now carry an immutable cutoff and ordered source
rows. Read-only reconciliation compares settlement classification, payment and
ledger totals, and the latest webhook consumer state. Reports keep JPY and USD
totals separate and expose expected and observed values without including test
tokens or signing secrets.

The browser checkout now accepts synthetic JPY and USD amounts in English or
Japanese. It converts the original amount string to integer minor units, blocks
normal repeated submission, preserves one idempotency key while a result is
uncertain, and restores a completed result after refresh. The checkout stores
only the active idempotency key and last payment ID in session storage.

Eight Gherkin acceptance scenarios run through Cucumber-JS and TypeScript
Playwright. They cover approval, decline, localized validation, exact currency
display, Japanese input, repeated submission, post-commit timeout recovery, and
a keyboard journey at a 390 by 844 responsive viewport. Failed scenarios retain
a screenshot and Playwright trace; Cucumber also produces HTML, JSON, and JUnit
reports.

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

The synthetic checkout is available at:

- <http://127.0.0.1:8000/checkout?lang=en>
- <http://127.0.0.1:8000/checkout?lang=ja>

Node 22, 24, or 26 and newer releases are supported by the browser test stack.
Install Chromium and run the complete browser gate:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

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

After authorization, use the returned payment ID for lifecycle operations:

```bash
curl --request POST http://127.0.0.1:8000/payments/PAYMENT_ID/capture \
  --header 'Idempotency-Key: demo-capture-0001'

curl --request POST http://127.0.0.1:8000/payments/PAYMENT_ID/refund \
  --header 'Content-Type: application/json' \
  --header 'Idempotency-Key: demo-refund-0001' \
  --data '{"amount": 1000}'
```

Use `/payments/PAYMENT_ID/cancel` instead of capture to cancel an authorized
payment. Capture and cancellation are mutually exclusive in the state machine.

See:

- [Payment requirements](docs/payment-requirements.md)
- [Payment lifecycle](docs/payment-lifecycle.md)
- [Idempotency and failure recovery](docs/payment-reliability.md)
- [Webhook delivery and consumption](docs/webhook-delivery.md)
- [Settlement and reconciliation](docs/reconciliation.md)
- [Risk-based test plan](docs/test-plan.md)
- [Quality evidence and milestone reports](docs/quality/README.md)
- [Defect reports](docs/defects/)

## License

This project is available under the [MIT License](LICENSE).
