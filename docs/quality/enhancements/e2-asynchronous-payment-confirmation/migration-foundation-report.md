# Enhancement 2 Database Migration Foundation Report

## Document information

| Field | Value |
|---|---|
| Enhancement | 2: Asynchronous payment confirmation |
| Foundation | Versioned database migration and startup validation |
| Result | Proceed to delayed-payment creation design review |
| Catalog commit | `069415e` |
| Migration commit | `6720c34` |
| Test commit | `628b000` |
| Pull request | [#19](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/19) |
| CI runs | [Functional and browser CI](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/33766751705) and [performance checkpoint](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/33766751562) |
| Local execution date | 2026-09-03 |

## Executive summary

The application now has an explicit database migration command and refuses to
start its normal HTTP service against an unversioned or outdated database. The
known older schema is upgraded without discarding existing payment evidence.
An unknown schema is rejected and is not marked current.

This foundation closes the local failure recorded in DEF-008 and makes future
asynchronous-confirmation schema changes reviewable as ordered revisions. It
does not implement `AWAITING_PAYMENT`, confirmation processing, expiry,
anomalies, races, cancellation, reconciliation changes, or new customer copy.

## Business problem

An older SQLite file allowed the checkout and health endpoint to look ready.
The first payment request then failed because the application queried a newer
idempotency column that the file did not contain. Table creation alone had been
mistaken for schema evolution.

Asynchronous confirmation will add several stored concepts. Continuing without
versioned migrations would make local demonstrations unreliable and make it
difficult to prove that existing payment evidence survives an upgrade.

## Implemented controls

- `payment-quality-lab-migrate` applies ordered revisions to the configured
  database before the service starts.
- The migration location is resolved from the installed package rather than the
  current shell directory.
- A fresh database receives the complete schema and revision marker.
- The known older schema receives lifecycle-idempotency and decline fields.
- Existing authorization idempotency records receive `AUTHORIZE` plus an
  immutable replay snapshot reconstructed from the related payment.
- Existing declined records without a reason receive the safe generic `unknown`
  reason in the payment and merchant projection.
- Unknown tables or columns stop adoption before the database is marked current.
- Normal service startup validates the head revision and fails with the exact
  migration command when it is missing.
- Disposable automated-test factories remain explicit and isolated.
- The performance harness upgrades its temporary database before starting its
  runtime application factory.

## Scenario results

| Scenario | Result | Evidence |
|---|---|---|
| `MIG-01` fresh initialization | Passed | Current tables and revision were created; health, checkout, and authorization worked |
| `MIG-02` known legacy upgrade | Passed | Two payments, one ledger effect, two webhook events, two projections, and two idempotency records remained |
| `MIG-03` repeated upgrade | Passed | The second run returned the same head revision and created no duplicate business data |
| `MIG-04` outdated startup | Passed | Application construction stopped with the migration instruction before serving |
| `MIG-05` post-migration startup | Passed | Health and checkout returned success; payment creation returned `AUTHORIZED` |
| `MIG-06` unknown schema | Passed | Migration raised an explicit error and left the recorded revision empty |
| `REG-M01` synchronous regression | Passed | Complete Python, browser, type, formatting, and performance-selection gates passed |

The legacy test goes beyond counting rows. It repeats the original authorization
with the same idempotency key and receives the original payment ID and replay
header. This proves the backfill retains observable recovery behavior.

## Automated evidence

| Evidence | Result |
|---|---|
| Focused migration suite | 4 passed, including strict resource-warning check |
| Complete Python suite | 268 passed |
| Branch-aware coverage | 89.87%; required minimum 85% |
| Node unit suite | 45 passed |
| TypeScript check | Passed |
| Cucumber-JS and Chromium | 11 scenarios and 100 steps passed |
| Ruff lint and formatting | Passed |
| Git diff check | Passed |
| Pull-request CI | Six checks passed: Python 3.12, Python 3.14, Chromium acceptance, performance selection, harness validation, and performance smoke |

The overall percentage decreased because the new migration environment and
revision scripts are loaded dynamically by Alembic and appear as uncovered in
the package-based coverage report. Their behavior is still executed through the
four database integration tests. The result remains above the declared gate;
no coverage exclusion was added to hide the difference.

## Data and privacy evidence

The upgrade stores no synthetic payment-method token, raw HTTP body, signature,
secret, or new customer identity. The reconstructed replay snapshot contains
only the payment fields that the API had already returned. Unknown database
shapes are not copied into the application schema.

The original local database was not modified during implementation. A copy was
upgraded successfully in a temporary directory, and the automated test uses a
reconstructed legacy database with non-empty business evidence.

## Limitations

- The migration evidence covers SQLite, which is the declared persistence
  system for this simulator. It is not evidence for another database engine.
- Only the known project-owned unversioned schema is adopted. Arbitrary older or
  manually altered schemas require investigation instead of guessed repair.
- Migration does not create an automatic backup. The operator documentation
  instructs users to back up meaningful local data first.
- Downgrade of the compatibility revision is intentionally rejected because the
  older schema cannot represent the retained replay evidence safely.
- This report closes only the migration foundation. Every asynchronous-payment
  scenario remains unpassed until its later implementation and evidence.

## Release recommendation

Proceed with the migration foundation. The explicit upgrade path resolves the
observed local failure, preserves known evidence, stops unknown schemas early,
and leaves synchronous payment behavior unchanged.

## Next review

Review `CONF-01` and `CONF-04` before implementation. The next change should
introduce `payment_flow`, `AWAITING_PAYMENT`, `payment_reference`, `expires_at`,
the initial awaiting webhook event, and creation replay without adding the
confirmation endpoint yet.
