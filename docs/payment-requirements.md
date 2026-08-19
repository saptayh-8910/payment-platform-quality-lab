# Payment Requirements and Testability Review

## 1. Purpose

This document defines the initial behavioral contract for a simulated payment
platform. It is intentionally provider-neutral and contains no real payment or
cardholder data.

Authorization, capture, cancellation, refund, concurrency hardening,
deterministic failure recovery, webhook delivery, and reconciliation are
implemented.

## 2. Domain model

### 2.1 Payment

A payment has:

- a server-generated unique identifier;
- a merchant reference;
- an amount expressed as a positive integer in minor units;
- an ISO 4217 currency code;
- a lifecycle status;
- authorized, captured, and refunded totals;
- created and updated timestamps;
- a monotonically increasing version for concurrency control.

Only `USD` and `JPY` are in the MVP scope. USD uses two decimal places. JPY is
zero-decimal. The API accepts integer minor units, so `1000 JPY` means 1,000 yen
and `1000 USD` means 10.00 US dollars.

### 2.2 Lifecycle states

The supported states are:

- `AUTHORIZED`
- `DECLINED`
- `CAPTURED`
- `PARTIALLY_REFUNDED`
- `REFUNDED`
- `CANCELLED`

The initial transition model is:

| Current state | Operation | Result |
|---|---|---|
| New request | Authorize successfully | `AUTHORIZED` |
| New request | Authorization declined | `DECLINED` |
| `AUTHORIZED` | Capture full authorized amount | `CAPTURED` |
| `AUTHORIZED` | Cancel | `CANCELLED` |
| `CAPTURED` | Refund less than captured amount | `PARTIALLY_REFUNDED` |
| `CAPTURED` | Refund full captured amount | `REFUNDED` |
| `PARTIALLY_REFUNDED` | Refund remaining amount | `REFUNDED` |
| `PARTIALLY_REFUNDED` | Refund less than remaining amount | `PARTIALLY_REFUNDED` |

All unlisted transitions must fail without changing payment or ledger state.
Partial capture is outside the MVP unless added through a reviewed requirement
change.

## 3. Functional requirements

### 3.1 Authorization

- A valid request creates one payment and one authorization ledger entry.
- An authorization decision must be deterministic under test control.
- A declined request creates a visible declined payment but no positive financial
  ledger effect.
- Invalid amount, currency, or merchant reference must be rejected before any
  payment or ledger record is created.

### 3.2 Capture and cancellation

- Only an authorized payment may be captured or cancelled.
- Capture must never exceed the authorized amount.
- A successful capture creates exactly one capture ledger entry.
- Cancelling an authorization creates one cancellation ledger entry and must
  prevent future capture.
- Repeating a successful operation with the same idempotency key must not create
  another ledger entry.

### 3.3 Refunds

- Only captured funds may be refunded.
- The cumulative refunded amount must never exceed the captured amount.
- Every successful refund creates one ledger entry with a unique operation ID.
- Full and partial refund states must agree with captured and refunded totals.
- Rejected and over-limit refunds must not change payment or ledger state.

### 3.4 Idempotency

- Every state-changing request requires an idempotency key.
- A repeated key with an equivalent request returns the original outcome.
- A repeated key with a different request fingerprint returns a conflict.
- Idempotency records and their financial changes must commit atomically.
- Concurrent equivalent requests with the same key must produce one financial
  effect.

### 3.5 Webhooks

- Successful lifecycle changes produce uniquely identified webhook events.
- Webhook payloads are signed; invalid signatures are rejected by the consumer.
- Delivery is at least once, so consumers must tolerate duplicates.
- Consumers must not assume delivery order.
- Failed deliveries are retried according to a deterministic test schedule.
- Reprocessing an event must not repeat its business effect.

### 3.6 Failure injection

Test-only controls will simulate:

- a timeout before persistence;
- a timeout after persistence but before the response;
- transient webhook delivery failure;
- duplicate and out-of-order webhook delivery;
- a reconciliation mismatch.

Failure controls must be unavailable when the application is not explicitly
running in a test or demonstration mode.

### 3.7 Reconciliation

- Payment totals, ledger entries, processed events, and simulated settlement
  records must be independently comparable.
- Reconciliation classifies records as matched, missing, duplicated, or
  amount-mismatched.
- A clean run balances exactly in integer minor units.
- Summary totals and discrepancies must remain separate for each currency.
- A mismatch report identifies the payment, source, expected value, and observed
  value without exposing sensitive data.

## 4. Financial invariants

The implementation and property-based tests must preserve these invariants:

1. Amounts and totals are integers greater than or equal to zero.
2. Authorized amount equals the original payment amount for an authorization.
3. Captured amount never exceeds authorized amount.
4. Refunded amount never exceeds captured amount.
5. A declined or cancelled payment cannot be captured.
6. One idempotent operation produces at most one financial ledger effect.
7. Replaying a webhook event does not change the final financial result.
8. Payment totals equal the sum of their applicable ledger entries.
9. A successful clean reconciliation has a net discrepancy of zero.
10. Invalid operations leave payment and ledger state unchanged.

## 5. Testability feedback and open decisions

Milestone 4 resolved the following decisions:

- Payment updates use optimistic locking through the aggregate version. A stale
  writer receives a retryable concurrency conflict.
- A unique idempotency claim is acquired before a financial mutation. Equivalent
  concurrent requests replay one immutable outcome.
- Idempotency records remain available indefinitely within the simulator.
- Declined authorizations replay the original decline response.

The webhook delivery slice resolved these decisions:

- Aggregate version is the main ordering value. Event time remains diagnostic.
- Events carry a full payment snapshot so a newer event can be applied when an
  earlier version is delayed.
- HMAC-SHA256 signatures cover the timestamp and exact raw body.
- Delivery retries every non-success result up to three deterministic attempts.
- The consumer inbox and merchant projection commit in one transaction.
- Settlement uses immutable ledger entries with `created_at <= cutoff`.
- Only payments with a positive net captured balance require a settlement row.
- Settlement source lines remain ordered so duplicate evidence is repeatable.
- Reconciliation is read-only and never creates a financial effect.
- JPY and USD totals are grouped separately; no cross-currency total is valid.

These are documented as testability concerns rather than silently embedded in
the implementation.

## 6. Security and privacy boundaries

- Test data must use synthetic customer and merchant values.
- The service must not accept PAN, CVV, or other cardholder data.
- Logs and reports must not contain secrets or webhook signing keys.
- This project demonstrates selected security-related tests but is not a security
  certification or production payment implementation.
