# Milestone 5 Webhook and Reconciliation Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Milestone | 5: Webhook delivery, consumption, and reconciliation |
| Status | Draft for review |
| Owner | Sapta Y Husain |
| Planned delivery | PR 4 for webhooks and PR 5 for reconciliation |
| Requirements | Webhooks, failure injection, and reconciliation in `docs/payment-requirements.md` |
| Previous evidence | [Milestone 4 quality report](../m4-idempotency-recovery/quality-report.md) |

## Executive summary

Payment platforms use webhooks to tell another system that a payment changed.
A webhook may arrive more than once, arrive late, or arrive in a different order.
The receiver must remain correct in all of these cases.

Reconciliation compares independent financial records. It should show whether
the payment, ledger, webhook projection, and settlement data agree. A clean run
must balance exactly in integer minor units.

This catalog records planned coverage. No scenario in this document is marked as
passed until implementation is complete and a closing report contains the
execution evidence.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| Webhook event is missing | Merchant does not learn that a payment changed | High |
| Forged or changed webhook is accepted | Merchant acts on false payment data | Critical |
| Duplicate event repeats a business effect | Duplicate fulfilment, notification, or accounting action | Critical |
| Events arrive out of order | Merchant view returns to an older payment state | High |
| Retry stops too early or never stops | Lost update or uncontrolled delivery traffic | High |
| Payment and settlement disagree | Accounting loss and operational investigation | Critical |
| Report exposes a secret | Security and privacy incident | High |

## Proposed design decisions

These decisions are recommendations. They must be reviewed before implementation.

### Transactional outbox

The payment, ledger entry, and webhook event should commit in one transaction.
This prevents a saved payment from existing without its event.

### Full payment snapshot

Each event should contain the full payment state after the operation. This allows
a newer event to establish the correct consumer view even when an earlier event
is delayed.

### Event ordering

The payment version should be the main ordering value. `occurred_at` should help
with investigation but should not decide which event is newer. Computer clocks
can differ, while the payment version increases inside the transaction.

### Event types

The proposed event types are:

- `payment.authorized`
- `payment.declined`
- `payment.captured`
- `payment.cancelled`
- `payment.refunded`

Partial and full refunds use `payment.refunded`. The payment status and totals in
the full snapshot show whether the refund is partial or complete.

### Signature

Use HMAC-SHA256 over `timestamp.raw_body`. Accept timestamps within a documented
five-minute tolerance. Tests use a synthetic secret that is never included in
payloads, reports, or logs.

### Delivery schedule

Use at-least-once delivery with three deterministic attempts: immediately, one
second later, and five seconds after that. Tests use a controllable clock and do
not sleep for real time.

### Consumer model

The consumer should store processed event IDs and a merchant-facing payment
projection. It should not modify the source payment or its financial ledger.

### Settlement cutoff

Settlement should use immutable ledger entries with `created_at <= cutoff`.
Expected settlement is captured funds minus refunds at that cutoff. A payment
with an expected balance of zero does not require a settlement row.

## Scope

The milestone covers event creation, signing, delivery attempts, retry state,
consumer verification, duplicate handling, ordering, settlement records, and
reconciliation reports.

It does not cover a real external merchant, internet delivery, production secret
management, cloud queues, multi-region ordering, browser checkout, or load
testing.

## 1. Webhook event generation

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| W01 | Authorization, decline, capture, cancellation, partial refund, or full refund succeeds | Exactly one correctly typed event is stored with the resulting payment version | Critical | Integration |
| W02 | An event is inspected after commit | It has a unique ID, payment ID, type, version, UTC time, and full payment snapshot | High | Unit and integration |
| W03 | An operation is rejected, such as a second capture or over-refund | No webhook event or partial financial state is stored | Critical | Integration |
| W04 | A successful request is repeated with the same idempotency key | The original result is replayed and no second event is created | Critical | API and integration |
| W05 | Two equivalent requests arrive together | One payment effect, ledger effect, idempotency result, and event are created | Critical | Integration |
| W06 | A timeout occurs before commit | No payment, ledger, idempotency, or webhook event remains | Critical | Integration |
| W07 | A timeout occurs after commit and the client retries | The event remains committed and the retry creates no duplicate | Critical | API and integration |
| W08 | Outbox persistence is forced to fail | The payment and ledger changes roll back with the event | Critical | Integration |

## 2. Webhook signatures

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| S01 | Consumer receives the original body with a valid timestamp and signature | Signature is accepted and processing may continue | Critical | Unit and API |
| S02 | Amount, status, payment ID, version, or body spacing changes after signing | Signature is rejected and no consumer state changes | Critical | Unit and API |
| S03 | Payload is signed with a different secret | Signature is rejected without exposing either secret | Critical | Unit |
| S04 | Signature header is missing or malformed | Consumer returns one clear validation error and does not fail internally | High | API |
| S05 | Timestamp is expired, too far in the future, or changed after signing | Event is rejected outside the allowed tolerance | High | Unit and API |

## 3. Delivery and retry

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| D01 | Consumer accepts the first delivery | One attempt is recorded and the event becomes delivered | High | Integration |
| D02 | First delivery fails but the next attempt succeeds | Failure and success are recorded at the deterministic retry times | High | Integration |
| D03 | Every delivery attempt fails | The maximum attempt count is enforced and the event becomes exhausted | High | Integration |
| D04 | Delivery receives a server error, timeout, connection error, or other configured failure | Each result follows one documented retry policy | High | Integration |
| D05 | Consumer commits the event but the producer loses the acknowledgement | Redelivery occurs, the consumer detects the duplicate, and the business effect remains once | Critical | End to end |
| D06 | Test mode requests duplicate or out-of-order delivery | Delivery follows the exact requested pattern and remains repeatable | High | Integration |
| D07 | Two dispatch workers try to claim the same pending event | One worker owns the active attempt and accidental parallel first delivery is prevented | High | Integration |
| D08 | One event continues to fail while other events are ready | Other eligible events continue and are not blocked by the failed event | Medium | Integration |

## 4. Consumer idempotency and ordering

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| C01 | A valid event arrives for the first time | One inbox record is stored and the merchant projection matches the event snapshot | High | Integration |
| C02 | The exact event is delivered again | Consumer acknowledges it safely and does not repeat the projection effect | Critical | Integration |
| C03 | Duplicate copies arrive at the same time | Unique event protection allows one processing transaction | Critical | Integration |
| C04 | Payment version 2 arrives after version 3 | Version 2 is recorded as stale and the projection remains at version 3 | High | Integration |
| C05 | Payment version 3 arrives before version 2 | The full version 3 snapshot establishes the latest view and the gap remains visible | High | Integration |
| C06 | The same event ID arrives with different content | Consumer reports an event collision and keeps the accepted result unchanged | Critical | Integration |
| C07 | A different event ID claims the same payment version with conflicting content | Consumer does not silently replace the existing projection | High | Integration |
| C08 | Event type, JSON, payment ID, version, currency, or amount is invalid | Event is rejected or quarantined and the projection does not change | High | API and integration |
| C09 | Consumer fails after starting its inbox and projection transaction | Both changes roll back and a later delivery can succeed | Critical | Integration |

## 5. Settlement and reconciliation

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| R01 | A captured payment has matching ledger, projection, and settlement data | Classification is `matched` and discrepancy is zero | Critical | Integration |
| R02 | A payment is partially refunded | Expected settlement equals capture minus cumulative refunds | Critical | Unit and integration |
| R03 | A payment is fully refunded | Expected balance is zero and no settlement row is required | High | Integration |
| R04 | A payment is declined or cancelled | No positive settlement is expected and the absence is matched | High | Integration |
| R05 | JPY and USD payments are reconciled | Integer minor units produce exact results without floating-point values | Critical | Unit and integration |
| R06 | An expected settlement row is absent | Classification is `missing` with payment and expected amount | Critical | Integration |
| R07 | More than one settlement row exists for one expected payment | Classification is `duplicated` without double-counting the report total | Critical | Integration |
| R08 | Settlement amount differs from the expected net amount | Classification is `amount_mismatched` with expected and observed values | Critical | Integration |
| R09 | Consumer projection is missing or behind the latest event | Report identifies the webhook source mismatch independently | High | Integration |
| R10 | Payment totals disagree with immutable ledger entries | Report identifies the exact source disagreement and does not trust one source silently | Critical | Integration |
| R11 | One batch contains matched, missing, duplicated, and mismatched records | Every payment and summary count receives the correct classification | Critical | Integration |
| R12 | Financial operations occur before, at, and after the cutoff | Only entries with `created_at <= cutoff` are included | High | Unit and integration |
| R13 | Reconciliation runs again with the same inputs and cutoff | The report is identical and creates no financial effects | Medium | Integration |
| R14 | A mismatch report is inspected | It is useful for investigation and contains no token or signing secret | High | API and manual review |

## Detailed centerpiece scenario

### D05: acknowledgement is lost after consumer processing

#### Business risk

A merchant may process a capture event successfully while the payment platform
times out waiting for the response. The platform must deliver the event again,
but the merchant must not repeat fulfilment or accounting work.

#### Preconditions

- A captured payment and its committed webhook event exist.
- Producer and consumer use the same synthetic signing secret.
- The consumer database is empty.
- Test mode can lose the first successful acknowledgement.

#### Steps

1. Dispatcher signs and sends the capture event.
2. Consumer verifies and commits the event and payment projection.
3. Test control removes the successful acknowledgement.
4. Producer records a timeout and schedules a retry.
5. Dispatcher sends the same signed event again.
6. Consumer finds the existing event ID and returns success without applying it
   again.
7. Producer marks the event as delivered.
8. Generate settlement data and run reconciliation.

#### Expected result

- Producer attempt history contains the timeout and later success.
- Consumer inbox contains one processed event.
- Merchant projection changes once.
- Core payment and ledger remain unchanged by delivery.
- Settlement matches captured funds.
- Reconciliation reports `matched` with zero discrepancy.

## Planned evidence

- Unit tests for signing, ordering decisions, cutoff rules, and classification.
- API tests for signature errors, validation errors, and report contracts.
- SQLite integration tests for outbox transactions, retry attempts, consumer
  inbox transactions, and reconciliation.
- One end-to-end acknowledgement-loss journey.
- JUnit and branch-aware coverage reports in GitHub Actions.
- A sanitized example mismatch report for human review.
- A closing quality report containing commit, PR, CI, defects, limitations, and
  release recommendation.

## Entry criteria

- Proposed design decisions are reviewed.
- Event payload and signature format are agreed.
- Retry schedule and maximum attempts are agreed.
- Ordering rule is agreed.
- Settlement cutoff and zero-balance rule are agreed.
- Deterministic clocks and failure controls are planned.

## Exit criteria

- All critical scenarios pass.
- No open critical or high defect lacks an agreed disposition.
- Duplicate and out-of-order delivery do not repeat a consumer effect.
- Invalid signatures create no inbox or projection state.
- A clean reconciliation reports zero discrepancy.
- Injected missing, duplicate, and amount mismatch records receive the correct
  classification.
- CI passes on supported Python versions.
- Logs and reports contain no token or signing secret.
- The closing report records actual evidence and limitations.

## Review questions

1. Should aggregate version be the main ordering value, with time used only for
   investigation?
2. Is a five-minute signature timestamp tolerance suitable for the simulator?
3. Should delivery use three attempts at immediate, plus one second, plus five
   seconds?
4. Should every non-success response be retried, or should some client errors
   stop immediately?
5. Should a newer full snapshot be applied when an earlier version is missing?
6. Should zero-balance payments have no settlement row?
7. Should ledger time at or before the cutoff be included?
8. Is splitting webhook work and reconciliation into PR 4 and PR 5 acceptable?
