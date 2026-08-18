# Idempotency and Failure Recovery

## Quality objective

Payment clients retry when responses are slow, lost, or ambiguous. The simulator
must therefore distinguish repeated delivery from a new financial instruction
and must prevent stale concurrent requests from overwriting newer payment state.

## Idempotency transaction

Every state-changing operation follows one transaction boundary:

1. Calculate a canonical request fingerprint.
2. Claim the unique idempotency key before changing payment state.
3. Replay the stored snapshot when the same key and fingerprint already exist.
4. Reject the key when its fingerprint identifies a different request.
5. Apply the payment transition and append its ledger entry.
6. Store an immutable response snapshot with the completed claim.
7. Commit the payment, ledger, idempotency record, and snapshot together.

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

The client receives `409 concurrent_payment_update` and should retrieve the
payment before deciding whether a new operation is still valid.

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
