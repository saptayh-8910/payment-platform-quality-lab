# DEF-008: Older local database failed only on payment submission

## Summary

The current checkout loaded normally against an older local SQLite database,
but the first payment submission returned HTTP 500. The application expected
new idempotency and decline columns that the existing database did not contain.

## Detection

| Field | Evidence |
|---|---|
| Enhancement | UX-01 interactive follow-up |
| Found by | Manual checkout submission through the running full-stack application |
| Severity | High for local reliability; no production system is claimed |
| Status | Resolution in E2 migration-foundation pull request |

## Reproduction

1. Keep a SQLite database created by an earlier project version.
2. Start the current application against that database.
3. Open the checkout and submit a valid synthetic approved payment.
4. Observe the general customer-safe error and the server-side database error.

The first observed missing field was `idempotency_records.operation`. Inspection
also found older schemas without `idempotency_records.response_snapshot` and
the payment and projection decline-reason fields.

## Expected result

An older supported schema should have an explicit, data-preserving upgrade
path. An unknown or unmigrated schema should stop startup with an actionable
message before the service reports itself ready.

## Observed result

`Base.metadata.create_all()` created absent tables but did not alter existing
tables. The checkout and health endpoint therefore appeared ready. Payment
submission later reached a query for a missing column and failed with HTTP 500.

## Root cause

The project had no schema-version record or migration command. Local startup
treated table creation as if it also provided database upgrades, but SQLAlchemy
`create_all()` does not migrate an existing table.

## Planned resolution

- Add versioned database migrations and an explicit migration command.
- Adopt only the known older schema shape; reject unknown shapes.
- Backfill the original authorization operation and immutable replay snapshot
  for legacy idempotency records.
- Preserve existing payment, ledger, webhook, projection, and idempotency data.
- Validate the schema revision before the local HTTP service starts.
- Add tests for fresh setup, legacy upgrade, repeatability, rejection, startup,
  and synchronous regression.

## Evidence boundary

The browser displayed the intended safe general error and did not expose the
database exception. That presentation behavior was correct, but it did not make
the backend failure acceptable. The migration tests and complete regression
gate will determine whether this defect is resolved.
