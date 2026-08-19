# Milestone 5 Quality Report

## Document information

| Field | Value |
|---|---|
| Milestone | 5: Webhook delivery, consumption, and reconciliation |
| Result | Proceed with documented limitations |
| Webhook feature commit | `4ad85fe` |
| Reconciliation feature commit | `229ed6b` |
| Pull requests | [PR #5](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/5) and [PR #6](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/6) |
| CI runs | [Webhook run 32096578249](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32096578249) and [reconciliation run 32216932206](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32216932206) |
| Execution date | 2026-08-19 |

## Executive summary

Milestone 5 met its quality objectives for this simulator. Payment changes now
create signed webhook events in the financial transaction. Delivery retries are
controlled and observable. The merchant consumer handles duplicates and old
events without repeating or reversing a business effect.

Reconciliation compares the payment, immutable ledger, latest webhook consumer
view, and synthetic settlement rows. It reports matching, missing, duplicate,
amount, currency, ledger, and projection problems with expected and observed
values.

The final suite contained 195 tests and reached 98.39% branch-aware coverage.
GitHub Actions passed on Python 3.12 and 3.14. Two genuine defects were found,
fixed, documented, and covered by regression tests.

The result supports progress to the English and Japanese checkout milestone. It
does not prove delivery through a real network or reconciliation with a real
bank or payment provider.

## Situation

A payment platform cannot assume that a successful database commit will produce
one successful notification. A merchant may receive the same event more than
once, receive events in a different order, or process an event before the
platform receives its acknowledgement.

Financial records may also disagree after payment processing. The payment row
may differ from its ledger, the merchant webhook view may be behind, or the
settlement file may be missing, duplicated, or incorrect.

Normal happy-path API tests do not expose these risks. The milestone needed
controlled failures and checks across independent data sources.

## Why these risks mattered

A repeated webhook effect can cause duplicate fulfilment or accounting work. An
old event can move a merchant view back to an incorrect state. A missing or
incorrect settlement can create a financial shortage that requires operational
investigation.

These failures affect merchant trust, customer experience, financial accuracy,
and incident response. Duplicate effects, forged events, and incorrect
reconciliation were treated as critical risks.

## Quality approach

The milestone combined several test levels because one level could not prove the
complete result:

- Unit tests checked exact raw-body signatures, timestamp tolerance, payload
  validation, cutoff rules, classifications, and integer currency behavior.
- File-backed SQLite integration tests used separate sessions for producer,
  consumer, and concurrent workers. This checked real commits, rollbacks,
  uniqueness rules, delivery leases, and read-only report behavior.
- API tests checked public status codes, validation messages, failure-control
  safety, response contracts, and secret-safe evidence.
- Controlled clocks tested retry and cutoff boundaries without real sleeps.
- Concurrency barriers forced overlapping dispatch and consumer requests.
- The acknowledgement-loss journey connected payment commit, delivery timeout,
  duplicate consumption, and final recovery.
- Reconciliation assertions compared every independent source instead of
  trusting one database row as the complete truth.

## Important decisions

### Transactional webhook outbox

The payment, ledger entry, idempotency result, response snapshot, and webhook
event commit together. A payment cannot be saved without its event.

### Full event snapshot and aggregate version

Every event contains the complete resulting payment view. Aggregate version is
the ordering rule, while event time supports investigation. A newer event can
establish the correct state even when an earlier event is delayed.

### At-least-once delivery

The producer makes up to three attempts: immediately, after one second, and
after another five seconds. An atomic lease prevents two workers from owning the
same active attempt. The consumer inbox makes exact redelivery safe.

### Exact signed bytes

HMAC-SHA256 covers the timestamp and exact raw body. The consumer verifies the
signature before parsing JSON and accepts timestamps only within five minutes.

### Immutable settlement batch

Each synthetic batch has one timezone-aware cutoff and ordered source lines.
Expected settlement uses ledger entries with `created_at <= cutoff`. A payment
with no positive captured balance does not require a row.

### Independent source checks

Settlement classification does not hide ledger or webhook problems. The report
shows payment and ledger totals separately, and it reports whether the latest
consumer event and projection are missing, stale, mismatched, or correct.

### Per-currency totals

JPY and USD totals are never added together. Expected, observed, and discrepancy
amounts are grouped by currency. This decision followed the genuine defect
recorded as DEF-004.

## Execution evidence

| Evidence | Result |
|---|---|
| Full automated suite | 195 passed |
| New reconciliation tests | 40 passed as part of the full suite |
| Branch-aware coverage | 98.39% |
| Reconciliation service coverage | 100% |
| API route coverage | 100% |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Python 3.12 CI | Passed |
| Python 3.14 CI | Passed |
| ResourceWarning-as-error run | Passed |
| Sanitized JSON artifact validation | Passed |
| Working tree whitespace check | Passed |

The approved scenarios and their automated files are mapped in the
[Milestone 5 scenario catalog](scenario-catalog.md). A sanitized
[mismatch report](example-mismatch-report.json) shows the investigation
contract without real payment or secret data.

## Defects and observations

Two genuine defects were observed during implementation.

### DEF-003: webhook lease timestamp comparison

The first atomic delivery lease caused SQLAlchemy to compare a timezone-aware
clock with a timezone-naive SQLite value in Python. Delivery stopped before the
consumer was called. The database now evaluates the lease condition, and the
session reloads the stored result. Delivery and concurrent-worker regression
tests pass. See [DEF-003](../../../defects/DEF-003-webhook-lease-datetime-comparison.md).

### DEF-004: mixed-currency reconciliation total

The first report design would have added JPY and USD minor units into one grand
total. The arithmetic was exact but financially meaningless. The report now
groups every total by currency and shows a wrong-currency row on both sides of
the discrepancy. See
[DEF-004](../../../defects/DEF-004-mixed-currency-reconciliation-total.md).

No critical or high defect remains open.

## Manual or exploratory evidence

The sanitized mismatch report was reviewed as a business investigation
artifact. The review confirmed that a reader can identify the payment, expected
amount, observed amount, settlement classification, ledger result, webhook
result, and currency discrepancy without reading test code.

The artifact was parsed with the standard JSON tool. Automated API checks also
confirmed that the report does not contain the synthetic payment token, webhook
signature header, or signing-secret prefix.

This was a focused evidence review, not the formal exploratory-testing session.
The broader exploratory charter remains planned for Milestone 7.

## Limitations

- SQLite provides deterministic local transactions but does not represent every
  production database lock or isolation behavior.
- Webhook delivery uses an in-process receiver rather than a real network,
  queue, DNS service, or merchant endpoint.
- The simulator uses one process and does not prove multi-region ordering.
- The settlement source is a synthetic JSON batch, not a bank or provider file.
- Fees, chargebacks, disputes, partial capture, reserves, and foreign-exchange
  conversion are outside the current scope.
- The report rejects unknown payments and does not model provider-only records.
- Tests use controlled failure points and cannot represent every infrastructure
  failure.
- The project does not claim production readiness or PCI DSS compliance.

## Release recommendation

Proceed to Milestone 6 with the stated limitations. All approved critical
webhook and reconciliation scenarios have automated evidence. Both supported CI
environments pass, the two observed high-severity defects are resolved, and the
remaining limitations match the declared scope of this privacy-safe simulator.

## Next quality risks

- English and Japanese checkout journeys may behave differently.
- Localized labels, errors, and input rules may be incomplete or unclear.
- Browser behavior may differ from direct API behavior.
- Keyboard navigation, focus order, and mobile layout need user-facing checks.
- The checkout must not introduce collection of real cardholder data.
