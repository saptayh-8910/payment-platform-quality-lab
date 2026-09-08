# Payment Requirements and Testability Review

## 1. Purpose

This document defines the initial behavioral contract for a simulated payment
platform. It is intentionally provider-neutral and contains no real payment or
cardholder data.

Authorization, asynchronous payment creation and confirmation, capture,
cancellation, refund, concurrency hardening, deterministic failure recovery,
webhook delivery, and reconciliation are implemented. Scheduled expiry and the
confirmation-versus-expiry race remain later reviewed work.

## 2. Domain model

### 2.1 Payment

A payment has:

- a server-generated unique identifier;
- a merchant reference;
- an amount expressed as a positive integer in minor units;
- an ISO 4217 currency code;
- a lifecycle status;
- a payment flow identifying synchronous or asynchronous confirmation;
- a unique payment reference and expiry time for an asynchronous payment;
- a normalized decline reason when the lifecycle status is `DECLINED`;
- authorized, captured, and refunded totals;
- created and updated timestamps;
- a monotonically increasing version for concurrency control.

Only `USD` and `JPY` are in the MVP scope. USD uses two decimal places. JPY is
zero-decimal. The API accepts integer minor units, so `1000 JPY` means 1,000 yen
and `1000 USD` means 10.00 US dollars.

### 2.2 Lifecycle states

The supported states are:

- `AUTHORIZED`
- `AWAITING_PAYMENT`
- `DECLINED`
- `CAPTURED`
- `PARTIALLY_REFUNDED`
- `REFUNDED`
- `CANCELLED`
- `EXPIRED`

The initial transition model is:

| Current state | Operation | Result |
|---|---|---|
| New request | Authorize successfully | `AUTHORIZED` |
| New request | Authorization declined | `DECLINED` |
| New asynchronous request | Request later confirmation | `AWAITING_PAYMENT` |
| `AWAITING_PAYMENT` | Matching confirmation before expiry | `CAPTURED` |
| `AWAITING_PAYMENT` | Confirmation at or after expiry | `EXPIRED` |
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
- Every declined payment stores one recognized provider-neutral reason.
- An authorized payment has no decline reason.
- The legacy `tok_declined` simulator control remains a backward-compatible
  alias for the safe `unknown` reason.
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

### 3.2.1 Asynchronous payment creation

- The provider-neutral `tok_awaiting_confirmation` simulator input creates an
  `ASYNCHRONOUS_CONFIRMATION` payment in `AWAITING_PAYMENT`.
- The synthetic input is fingerprinted for idempotency and is not retained.
- The payment receives a unique `ref_` reference and expires 72 hours after the
  injected creation time.
- The 72-hour duration represents a delayed customer action. Automated tests
  move the clock directly and do not wait for this interval.
- Creation produces no authorization, capture, refund, or ledger effect.
- Creation emits one `payment.confirmation_requested` event in the same
  transaction as the payment and idempotency result.
- An identical retry returns the original payment ID, reference, timestamps,
  and expiry. Conflicting key reuse returns `409` without another effect.
- `payment_flow` is descriptive metadata. It does not select a different
  financial-invariant regime; every payment retains the shared
  `captured_amount <= authorized_amount` rule.
- The separate confirmation identity protects this inbound event from replay;
  it does not reuse the client payment-operation idempotency key.

### 3.2.2 Asynchronous payment confirmation

- The confirmation sender supplies a unique confirmation ID, payment reference,
  positive integer amount, and supported currency.
- `Confirmation-Signature` covers the timestamp and exact raw request body with
  the shared HMAC-SHA256 format. The confirmation boundary uses its own
  synthetic secret.
- Missing, malformed, stale, future, or incorrect signatures return `401`
  before the body is parsed or any evidence is stored.
- The server assigns `received_at` from an injected clock. Caller-supplied time
  is not accepted.
- A matching confirmation received before expiry changes the payment directly
  from `AWAITING_PAYMENT` to `CAPTURED`. Authorized and captured amounts are set
  together so the shared financial invariant remains valid.
- The transaction creates one `CONFIRMATION_CAPTURE` ledger entry and one
  `payment.captured` event. A partial failure rolls back every effect.
- An identical confirmation replay returns the original generic acknowledgement
  and creates nothing else. Reusing the ID with changed content returns `409`.
- Late, amount-mismatched, currency-mismatched, unknown-reference, and
  already-resolved confirmations receive an internal durable disposition but
  no unintended financial effect.
- A late confirmation can apply the shared transition to `EXPIRED`. The
  separate scheduled-expiry operation and forced race test remain pending.
- External responses contain only `accepted: true`. Internal classification is
  retrieved separately so callers cannot probe payment state.
- The raw request body and signature are not retained.

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
- A declined full-snapshot event contains the same normalized reason as the
  payment; non-declined events contain no decline reason.
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

Enhancement 1 resolved these decisions:

- `DECLINED` remains one lifecycle state; a separate normalized reason explains
  why the attempt was declined.
- Six provider-neutral reasons are supported: insufficient funds, limit
  exceeded, expired payment method, failed verification, invalid payment
  method, and unknown.
- The normalized reason is preserved in payment retrieval, idempotent response
  snapshots, webhook events, and merchant projections.
- Customer guidance maps the reason to reviewed English or Japanese text and
  never displays the machine-readable code directly.
- Identical idempotent retries return the original reason. Reusing the key with
  a changed token, amount, currency, or merchant reference returns a conflict.

These are documented as testability concerns rather than silently embedded in
the implementation.

## 6. Security and privacy boundaries

- Test data must use synthetic customer and merchant values.
- The service must not accept PAN, CVV, or other cardholder data.
- Logs and reports must not contain secrets or webhook signing keys.
- Submitted simulator tokens must not appear in retained API evidence, webhook
  payloads, browser storage, screenshots, traces, or reports.
- This project demonstrates selected security-related tests but is not a security
  certification or production payment implementation.
