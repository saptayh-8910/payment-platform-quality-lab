# DEF-002: Failed operation can retain an idempotency claim in the session

## Summary

The new claim-first idempotency flow inserted and flushed a key before validating
the payment transition. When validation failed in a caller-managed database
session, the service raised the expected error but did not roll back the claim.

## Discovery

- Milestone: M4 idempotency and failure recovery
- Found by: persistence integration regression suite
- Environment: SQLite in memory, SQLAlchemy caller-managed session
- Severity: Medium
- Status: Resolved before PR #3 was merged

## Impact

No payment or ledger change was committed. However, the same session still held
an incomplete idempotency claim. If a caller caught the validation error and
later committed unrelated work in that session, the unused key could be saved
without a payment outcome. A later retry could then fail instead of running
safely.

The FastAPI request session normally rolled back after the exception. The defect
was still important because the payment service can be called directly by tests,
tools, or future background workers.

## Reproduction

1. Authorize and capture a payment in one caller-managed session.
2. Attempt a second capture with a new idempotency key.
3. Catch the expected invalid-transition error.
4. Count the idempotency records in the same session.

Expected: only the authorization and first capture keys remain.

Observed: a third incomplete key from the rejected capture remained in the
transaction.

The failing regression assertion expected two idempotency records but observed
three.

## Root cause

The service correctly claimed the unique key before the financial mutation. It
then validated the lifecycle transition. The invalid transition raised an
exception before the common commit helper ran, so the helper could not perform
its rollback.

Rollback behavior existed at the HTTP request boundary, but it did not exist at
the payment service boundary where the claim was created.

## Resolution

Claimed authorization and lifecycle operations now execute inside service-level
error handling. If validation or persistence fails while a transaction remains
open, the service rolls back the complete transaction before returning the
error.

This keeps the claim, payment mutation, and ledger mutation inside one atomic
outcome for API requests and direct service callers.

## Regression evidence

- `test_invalid_transition_leaves_all_persisted_state_unchanged` confirms that a
  rejected second capture leaves only the accepted idempotency records.
- `test_invalid_authorization_rolls_back_its_idempotency_claim` confirms that an
  invalid authorization leaves no payment, ledger, or idempotency record.
- The final Milestone 4 suite passed on Python 3.12 and 3.14.

## Learning

Transaction safety must be enforced in the layer that starts the transaction
work. Request-level cleanup is useful, but it should not be the only protection
for a reusable service function.
