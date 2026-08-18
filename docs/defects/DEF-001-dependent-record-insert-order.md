# DEF-001: Authorization fails with foreign-key enforcement enabled

## Summary

The authorization transaction attempted to insert an idempotency record before
its new parent payment row had been persisted. Once SQLite foreign-key
enforcement was enabled, valid authorizations failed with an integrity error.

## Discovery

- Milestone: M2 authorization vertical slice
- Found by: automated API and persistence integration tests
- Environment: SQLite with `PRAGMA foreign_keys=ON`
- Severity: High
- Status: Resolved

## Impact

Every approved or declined authorization failed before commit when database
foreign keys were enforced. No partial payment, ledger, or idempotency data was
committed, but the authorization API was unavailable for valid requests.

## Reproduction

1. Enable SQLite foreign-key enforcement for each database connection.
2. Submit a valid authorization with a new idempotency key.
3. Observe `FOREIGN KEY constraint failed` while inserting the idempotency row.

Expected: the payment, applicable ledger entry, and idempotency record commit as
one atomic outcome.

Observed: the dependent idempotency insert was attempted before its referenced
payment row existed in the database.

## Root cause

The service assigned the payment ID in application code and added payment,
ledger, and idempotency ORM objects to one session. The ORM did not have a
relationship path for the idempotency object that guaranteed the required flush
order. This remained invisible while SQLite foreign-key enforcement was off.

## Resolution

The service now flushes the parent payment row before adding dependent ledger
and idempotency rows. The flush remains inside the same database transaction; a
single final commit still makes the complete financial outcome atomic.

SQLite foreign-key enforcement remains enabled rather than weakening the
database to accommodate the original behavior.

## Regression evidence

- API authorization tests exercise approved, declined, replayed, and conflicting
  requests with foreign keys enabled.
- The persistence integration test verifies that payment, ledger, and
  idempotency records commit together.
- A negative integration test verifies that an orphan idempotency record is
  rejected by the database.
