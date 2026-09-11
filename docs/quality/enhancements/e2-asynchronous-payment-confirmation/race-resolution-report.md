# E2 race resolution and recovery report

Status: Local evidence recorded; pull-request CI pending.
Branch: `codex/e2-race-resolution`. Date: 2026-09-11.
Approved scope: [RACE-01 review](race-resolution-review.md), cases A through N.

## Business outcome

A matching confirmation accepted before the deadline can finish after the
deadline. While its committed receipt is pending, neither an expiry sweep nor
a late confirmation can close the payment. Capture still creates one ledger
entry and one lifecycle event.

Before this change, receipt and capture committed together. There was no
durable pending work to protect or resume. Now receipt commits first, and final
processing commits the payment, ledger, event, final disposition, and receipt
completion together. If processing fails, the receipt remains pending and the
HTTP response is a generic `503`. It never exposes the underlying error text.

## Decisions and limits

SQLite `BEGIN IMMEDIATE` reserves the writer before receipt acceptance,
completion, or expiry selection. The acceptance clock is sampled after writer
admission. That timestamp becomes durable if receipt commit succeeds. It is
not an exact disk commit timestamp: a receipt admitted before the deadline may
commit after it while expiry waits behind the same writer reservation.

This ordering definition prevents a timestamp sampled before lock waiting from
overriding an expiry that already won. A failed receipt commit creates no
protection. Request authentication uses its own current-time check before
receipt admission; raw signature and body are not retained.

The mechanism follows [SQLite transaction documentation](https://www.sqlite.org/lang_transaction.html).
It serializes database writers, including unrelated payments. This is a
throughput tradeoff for this simulator, not evidence of distributed or other
database-engine correctness. The configured busy timeout bounds lock waiting;
database admission errors return a retryable HTTP failure.

`CONFIRMATION_CAPTURE` remains a distinct ledger operation. Its transition sets
both balances and reconciliation counts it toward both totals. The shared
financial invariant has not changed.

## Executed scenario mapping

| Case | Evidence |
|---|---|
| A/B | A sender commits receipt and waits on an event. Another connection verifies the pending receipt. Expiry runs before or after completion; both produce one capture. |
| C | No receipt: expiry produces one event and no ledger entry. |
| D | At and after the deadline, with both processing orders: late disposition, one expiry, no capture. |
| E | Expiry pauses after candidate selection inside its write transaction. A distinct connection attempts admission. Its acceptance clock has not run while blocked; after expiry commits it samples a later time and records late. |
| F | Caller replay competes with completion of the same pending receipt; one effect and original time remain. |
| G | Changed content under a pending ID conflicts and preserves the original receipt. |
| H | Two accepted matching IDs compete; one applies and one records already resolved. |
| I | Original sessions and connections close. New connections recover the pending receipt; a second recovery finds no work. |
| J | Event failure leaves receipt pending and no partial ledger, final disposition, or lifecycle event. Recovery completes once. |
| K | Pending amount or currency mismatch does not protect expiry. Submitted values remain queryable. Existing terminal-state precedence classifies processing against EXPIRED as late. |
| L | API invalid signatures and malformed authenticated payloads store no receipt and cause no financial changes. |
| M | Caller retry competes with the internal recovery path; one final effect. |
| N | Two expiry sweeps overlap at the mutation checkpoint; first expires once, second rechecks and finds no eligible work. |

Additional tests cover late-confirmation protection, bounded recovery, failed
receipt commit, recovery failure, unknown receipts, invalid limits, dirty-session
rejection, safe HTTP retry, and migration from revision 0004. Migration preserves
historical final rows and backfills them as completed receipts; they never become
new recovery work. Existing pending/final schema upgrades remain repeatable.

The concurrency tests use a temporary file-backed SQLite database, separate
sessions, and distinct physical connections. Events have bounded waits. The
contender must reach its BEGIN checkpoint before the owner is released. Tests
use no sleep-based timing assumptions. These are service-level concurrency tests;
the HTTP regression verifies authentication, acknowledgement, failure, and retry.

## Local verification

- Python suite: 357 passed in the current execution.
- Branch-aware coverage: 85.88%; minimum 85%.
- Node: 45 tests passed. TypeScript, Ruff lint/format, and diff checks passed.
- Chromium: 11 Cucumber scenarios and 100 steps passed.
- Pull-request CI: pending.

## Recovery operation

After running the normal database migration, an internal operator can invoke:

```python
from payment_quality_lab.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from payment_quality_lab.services.confirmations import recover_pending_confirmations

engine = create_database_engine("sqlite:///payment_lab.db")
try:
    with create_session_factory(engine)() as session:
        completed_ids = recover_pending_confirmations(session, limit=100)
        print(completed_ids)
finally:
    engine.dispose()
```

Use a clean dedicated session. The operation selects pending receipts in
acceptance-time and ID order. Each completion is atomic. If an item fails,
earlier completed items remain committed and the failed item remains pending.
Retry skips completed work. Permanent processing failures require investigation;
there is no automatic background worker or claim that recovery runs unattended.

`GET /internal/confirmation-receipts/{id}` exposes receipt time and completion
status. The existing final diagnostic exposes disposition and submitted values.
These are internal simulator surfaces without production access control.

## Release boundary

This slice establishes the listed SQLite interleavings. It does not complete
awaiting cancellation, confirmation reconciliation reporting, localized guidance,
or exploratory closeout. Existing reports for PRs #22 and #23 remain historical
evidence; their single-transaction rollback and pending-race limitations are
superseded by this report.
