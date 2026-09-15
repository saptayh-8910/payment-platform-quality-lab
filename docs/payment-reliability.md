# Idempotency and Failure Recovery

## Quality objective

Payment clients retry when responses are slow, lost, or ambiguous. The simulator
must therefore distinguish repeated delivery from a new financial instruction
and must prevent stale concurrent requests from overwriting newer payment state.

## Idempotency transaction

Payment creation, capture, cancellation, and refund requests use an idempotency
key to recognise a repeated request and return its original result. These
requests follow one transaction boundary:

1. Calculate a canonical request fingerprint.
2. Claim the unique idempotency key before changing payment state.
3. Replay the stored snapshot when the same key and fingerprint already exist.
4. Reject the key when its fingerprint identifies a different request.
5. Apply the payment transition, create its webhook event, and append a ledger
   entry where required.
6. Store an immutable response snapshot with the completed claim.
7. Commit the payment, event, any ledger entry, idempotency record, and snapshot
   together.

Delayed-payment confirmation uses two separate database transactions:

1. Save the authenticated confirmation receipt.
2. Process the receipt and save its final result.

This separation prevents accepted work from being lost if processing fails.
A retry or recovery operation uses the original saved receipt time. Final
processing commits the payment change, any financial entry, webhook event,
and completed receipt result together. Some results, such as an unmatched
reference, do not change a payment or create a financial entry. See the
[payment lifecycle guide](payment-lifecycle.md) for confirmation and recovery.

Two concurrent equivalent requests can both inspect the database before either
has committed. The unique claim makes one request the owner; the other waits for
the transaction and then replays its completed response. Rolled-back claims are
not visible and do not block a later safe retry.

Response snapshots intentionally preserve the original outcome. For example,
replaying an authorization after capture returns the original `AUTHORIZED`
version 1 response while a normal payment retrieval returns the current
`CAPTURED` version 2 aggregate.

## Competing updates

The payment `version` is an optimistic-lock token. Each update includes its
previous version in the database write. If another request commits first, the
stale update affects no payment row, and the complete losing transaction rolls
back, including its ledger entry and idempotency claim.

This protects competing operations with different idempotency keys, such as:

- capture racing with cancellation;
- two refunds whose combined value exceeds the captured amount; and
- a stale operation attempting to overwrite a newer refund total.

A rejected stale update returns `409 concurrent_payment_update`. The client
should retrieve the payment before deciding whether a new operation is valid.

Delayed confirmation, expiry, and cancellation also coordinate their database
writes. A saved, matching confirmation received before the deadline protects
the payment from expiry and cancellation while processing is pending.
The response depends on the operation and the state it finds; not every
competing request returns the same conflict error.

## Deterministic timeout controls

Tests may explicitly select one of two failure points:

| Failure point | Persisted result | Safe client behavior |
|---|---|---|
| `before_commit` | No payment, ledger, or idempotency effect | Retry with the same key |
| `after_commit` | Complete financial outcome and response snapshot | Retry with the same key |

The HTTP control uses `X-Payment-Lab-Failure`. It returns `504 payment_timeout`
to model the client's uncertain outcome. The header returns
`403 failure_injection_disabled` unless `create_app()` was explicitly called
with `enable_failure_injection=True`; the default application cannot activate
the control.

Run the focused evidence with:

```bash
python -m pytest \
  tests/integration/test_payment_reliability.py \
  tests/api/test_failure_recovery.py
```

The tests use independent sessions over a temporary file-backed SQLite database
and synchronization barriers rather than timing sleeps. Assertions inspect the
payment aggregate, ledger, idempotency records, response snapshots, and version
so a successful HTTP status alone is never treated as proof of financial
correctness.
