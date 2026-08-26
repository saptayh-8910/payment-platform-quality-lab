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

- pytest for domain, API, database, webhook, and reconciliation testing.
- FastAPI TestClient for service-level HTTP checks.
- Node's built-in test runner for browser-side money rules.
- Cucumber-JS for business-readable Gherkin scenarios and scenario reports.
- TypeScript Playwright for Chromium control, isolated contexts, mobile and
  keyboard actions, network routing, screenshots, and traces.
- Hypothesis for financial and state-machine invariants.
- Grafana k6 OSS v2.0.0 for isolated performance and reliability profiles.
- Ruff and branch-aware coverage for fast feedback.
- GitHub Actions for Python, Chromium, automatic performance checkpoints, and
  retained test evidence.

## Delivery milestones

1. Project foundation, requirements, and risk-based test plan
2. Authorization vertical slice with persistence and CI
3. Payment lifecycle and financial invariants
4. Idempotency, ledger correctness, concurrency, and failure injection
5. Webhook delivery, consumption, and reconciliation
6. English/Japanese checkout with TypeScript Playwright and Cucumber-JS
7. Structured exploratory testing, cross-layer diagnosis, and defect evidence
8. Performance baseline and portfolio-ready reporting

## Current status

The service implements deterministic authorization and decline behavior plus
full capture, pre-capture cancellation, and partial or full refunds. Every
accepted lifecycle operation records one immutable ledger entry, increments the
payment version once, and commits its idempotency record in the same transaction.
Invalid transitions and over-refunds leave payment and ledger state unchanged.

The current automated baseline contains 231 pytest tests with 96.74%
branch-aware coverage, 17 Node money tests, and 8 Cucumber scenarios with 60
steps. GitHub Actions runs the Python suite on Python 3.12 and 3.14 and runs the
complete browser gate in Chromium.

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
uncertain, and restores uncertain or completed results after refresh. During an
uncertain result, tab-scoped session storage holds the active key and a minimal
synthetic retry packet: reference, integer amount, currency, and an approval or
decline choice. It does not store the raw API token. A final result clears that
packet and keeps only the last payment ID needed for refresh.

Eight Gherkin acceptance scenarios run through Cucumber-JS and TypeScript
Playwright. They cover approval, decline, localized validation, exact currency
display, Japanese input, repeated submission, post-commit timeout recovery
across refresh, and a keyboard journey at a 390 by 844 responsive viewport.
Failed scenarios retain a screenshot and Playwright trace; Cucumber also
produces HTML, JSON, and JUnit reports.

Milestone 7 is closed with an executed exploratory session, timestamped notes,
finding classification, privacy review, and cross-layer financial evidence. The
session found one High recovery defect: refresh hid an uncertain payment that
had already committed. The defect was reproduced in English and Japanese, fixed,
and added to the critical Cucumber regression journey. No duplicate financial
effect occurred.

Milestone 8 now has a local k6 harness for authorization, retrieval, concurrent
idempotent retry, and a mixed read/write workload. A loopback-only runner starts
FastAPI with a fresh temporary SQLite database. k6 checks exact traffic, HTTP
behavior, dropped work, and response time. An independent Python verifier then
checks payment, ledger, idempotency, webhook, and currency evidence. Both
sanitized reports must agree before the run passes.

The performance workflow runs the short smoke checkpoint for relevant pull
requests. A reviewer can manually select one profile or the full set, and a
weekly run provides an early warning for changes in speed or financial
reliability. Each profile uploads sanitized evidence before GitHub enforces the
final pass or fail decision.

Milestone 8 is closed with two complete passing baselines on merged code. Every
profile had zero HTTP failures, zero dropped iterations, and exact post-load
financial evidence. One intervening authorization execution exceeded its p99
guardrail while keeping correct financial records. The workflow blocked that
run, retained the evidence, and later passed a focused confirmation and a second
complete baseline without changing the thresholds. The
[Milestone 8 quality report](docs/quality/milestones/m8-performance-baseline/quality-report.md)
records the results, variation, limitations, and final recommendation.

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

The complete browser gate runs these commands in order:

```bash
npm run test:unit
npm run typecheck
npm run test:acceptance
```

Grafana k6 OSS v2.0.0 is required for the performance harness. Run the short
profile after installing that exact version:

```bash
python scripts/run_performance.py smoke
```

The measured profile names are `authorization`, `retrieval`,
`idempotent-burst`, and `mixed`. Every run creates its own loopback application
and temporary database. See the
[Milestone 8 implementation guide](docs/quality/milestones/m8-performance-baseline/implementation-guide.md)
for workloads, commands, evidence fields, safety controls, and limitations.

After the performance workflow is available on `main`, use its **Run workflow**
button to select one profile or `all`. Relevant pull requests run `smoke`
automatically. The weekly workflow runs the complete set without delaying every
code review.

Generated reports are local or temporary CI evidence and are not committed:

- `reports/junit.xml` and `reports/coverage.xml` for pytest;
- `reports/cucumber/cucumber-report.html` for a readable scenario report;
- `reports/cucumber/cucumber-report.json` for later analysis;
- `reports/cucumber/cucumber-junit.xml` for CI integration; and
- `reports/browser/` for sanitized failure screenshots and traces;
- `reports/performance/*/*/k6-summary.json` for selected performance metrics;
  and
- `reports/performance/*/*/financial-verification.json` for exact post-load
  financial checks.

GitHub Actions keeps Python, browser, and performance evidence for 14 days.
Human-readable milestone decisions remain under `docs/quality/` so a reviewer
can understand the risks, results, defects, and limitations without downloading
CI artifacts.

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
- [Final project quality summary](docs/quality/project-summary.md)
- [Milestone 6 checkout quality report](docs/quality/milestones/m6-multilingual-checkout/quality-report.md)
- [Milestone 7 exploratory charter](docs/quality/milestones/m7-exploratory-testing/exploratory-charter.md)
- [Milestone 7 session record](docs/quality/milestones/m7-exploratory-testing/session-record.md)
- [Milestone 7 quality report](docs/quality/milestones/m7-exploratory-testing/quality-report.md)
- [Milestone 8 performance scenario catalog](docs/quality/milestones/m8-performance-baseline/scenario-catalog.md)
- [Milestone 8 performance implementation guide](docs/quality/milestones/m8-performance-baseline/implementation-guide.md)
- [Milestone 8 performance quality report](docs/quality/milestones/m8-performance-baseline/quality-report.md)
- [Milestone 8 sanitized example summary](docs/quality/milestones/m8-performance-baseline/example-summary.json)
- [Defect reports](docs/defects/)

## License

This project is available under the [MIT License](LICENSE).
