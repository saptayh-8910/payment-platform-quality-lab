# RACE-01: Confirmation and expiry review

Status: Design decisions and scenarios approved on 2026-09-11. Implementation and execution evidence are
recorded in [the race report](race-resolution-report.md).

## Business purpose

A matching confirmation accepted before the deadline must still complete if
processing is delayed. Expiry must not close that payment while accepted work
is waiting. A confirmation accepted at or after the deadline is late.

Example: the deadline is 12:00. A matching confirmation is durably accepted at
11:59:59. Processing pauses, and expiry runs at 12:00. Expiry must skip this
payment. Processing later captures it once.

## Verified gap in the merged implementation

The baseline is main at `6e2b7fb`, after PR #23.

`process_confirmation` stores the final confirmation disposition, payment
change, ledger entry, and webhook in one transaction. The confirmation table
requires a final disposition. There is no separately committed pending receipt.
`expire_due_payments` selects by payment status and deadline only.

The existing catalog requires a test that pauses processing after durable
receipt. The current transaction cannot provide that pause point. Version
checks alone do not prove that an accepted on-time confirmation wins.

## Proposed contract

### Existing ledger decision

`CONFIRMATION_CAPTURE` is a distinct ledger operation, not audit metadata on
`CAPTURE`. The existing `capture_confirmation` function sets authorized and
captured amounts together. Reconciliation counts this operation toward both
totals. Ordinary `CAPTURE` consumes an existing authorization and contributes
only to the captured total.

Both paths enforce the same financial invariant. The canonical catalog already
specifies this operation, and PR #22 implemented it. This proposal retains that
design; it does not introduce it. The approved decision retains
`CONFIRMATION_CAPTURE` as a separate ledger operation. The existing
`captured_amount <= authorized_amount` rule applies to every payment flow;
there is no separate financial rule for delayed payments.

### Receipt and processing rules

1. Authenticate and validate before storing a receipt.
2. Persist immutable receipt evidence before final processing. Keep processing
   status separate from the existing final business dispositions. Pending is
   work status, not a new anomaly or financial outcome.
3. Coordinate receipt acceptance and expiry through the same database-level
   ordering mechanism. Expiry must not select a payment and later expire it
   using a stale decision after a qualifying receipt has been accepted.
4. Read a trusted acceptance clock inside that coordinated boundary. Keep
   request-arrival time separate if retained. A timestamp read before a wait
   for the database is not, by itself, proof of durable acceptance.
5. A committed, matching, on-time pending receipt protects an awaiting payment
   from expiry. A mismatch, invalid request, or late receipt does not.
6. Final processing commits the payment change, ledger, lifecycle event, final
   disposition, and receipt completion together. Preserve the existing shared
   financial invariant and one `CONFIRMATION_CAPTURE` entry.
7. Return the existing success acknowledgement only after final processing.
   If processing fails after receipt persistence, retain the pending work and
   return a retryable failure. An identical retry resumes that receipt using
   its original accepted time. Conflicting content returns a conflict.
8. Provide an explicit bounded recovery operation for committed pending work.
   Recovery must not depend entirely on the external sender retrying.

This changes the previous rollback contract: final processing failure leaves
the durable receipt, but no partial financial or lifecycle effect. Tests and
documentation must state that change explicitly.

## Scenarios for approval

These are review subcases of RACE-01; they do not replace existing scenario IDs.

| Case | Controlled situation | Required evidence |
|---|---|---|
| A | On-time matching receipt commits; processing pauses; expiry runs | Expiry skips it; resumed processing captures once |
| B | Same accepted receipt, but final processing runs before expiry | Same final balances, version, and event counts as A |
| C | No accepted on-time receipt; expiry runs at deadline | One expiry event; no ledger entry |
| D | Receipt accepted exactly at or after deadline; vary processing order | Late disposition; one expiry transition; no capture |
| E | Expiry has selected a candidate while receipt acceptance competes | Database coordination prevents a stale expiry decision; winner follows the defined acceptance boundary |
| F | Two identical deliveries overlap while receipt is pending | One receipt and one final effect; original accepted time retained |
| G | Same confirmation ID is reused with changed content while pending | Conflict; original receipt and payment preserved |
| H | Two distinct matching confirmation IDs compete for one payment | One capture; other final disposition records already resolved |
| I | Process stops after durable receipt, before final processing | New session finds pending work; recovery completes it once |
| J | Final event creation fails, then recovery runs | Financial transaction rolls back; receipt survives; retry completes once |
| K | On-time mismatch is pending when expiry runs | Mismatch does not protect payment from expiry; evidence remains queryable |
| L | Invalid signature or invalid payload | No receipt, no protection from expiry, no financial effect |
| M | Caller retry and internal recovery compete for the same pending receipt | Both use the same processing coordination; one final effect and no lost receipt |
| N | Two expiry sweeps overlap on the same due candidates | One expiry transition and event per payment; conflicts or retries are explicit and leave no partial batch effects |

## How the tests will force the race

Use a temporary file-backed database, independent sessions and connections,
and explicit synchronization events with bounded waits. A second connection
must observe the committed receipt before the paused-processing case continues.
Tests must verify that the competing operation reached the intended checkpoint.
Launching two threads or sleeping for an estimated duration is insufficient.

Cases A and E need different checkpoints. In A, receipt commit is complete and
visible before expiry begins, while financial processing is paused. In E, an
expiry candidate has been discovered and receipt acceptance competes before the
expiry mutation. The latter must force the coordination mechanism to recheck
eligibility or demonstrate that acceptance is blocked until the expiry decision
finishes. Reusing A's test under a second name would not prove E.

Inspect final payment state, receipt status, final dispositions, ledger entries,
and webhook versions from a fresh session. Exercise recovery after closing the
original session. Existing sequential tests remain regression coverage.

## Tradeoffs and review boundary

This preserves the intended receipt-before-processing rule but adds persisted
work state, migration, recovery, and contention handling. A failing pending
receipt can keep a payment awaiting until recovered; diagnostic visibility and
recovery are therefore part of this slice.

The implementation uses SQLite `BEGIN IMMEDIATE` before receipt acceptance,
completion, or expiry selection. Acceptance time is sampled after writer
admission and becomes durable only if that transaction commits. This is an
ordering timestamp within the transaction, not a measurement of disk commit
completion. SQLite evidence establishes behavior for this simulator; it does
not establish behavior for a different database engine.

The proposed scope is one persisted receipt mechanism, one bounded recovery
operation, and the listed forced interleavings. It does not add a queue broker,
distributed workers, or deployment infrastructure. Building this scope is
recommended to fulfill the existing durable-receipt requirement. Choosing the
simpler existing transaction instead would require revising that requirement
and recording the resulting limitation explicitly.

The separate `CONFIRMATION_CAPTURE` operation and the receipt-and-recovery
rules, including the 14 test cases, were reviewed and approved before
implementation.
