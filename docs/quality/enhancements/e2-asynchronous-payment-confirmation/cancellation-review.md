# CANC-01: Awaiting-payment cancellation review

Status: Owner approved on 2026-09-11. See [execution report](cancellation-report.md).
Baseline: merged PR #24, main `f9c87a3`. Date: 2026-09-11.

## Business purpose

A merchant can stop an unpaid payment request. Cancellation must not claim
that money was released when none was reserved. It must also not discard an
accepted confirmation just because its processing has paused.

This is a simulator policy, not a claim about any provider's cancellation rules.

## Verified baseline

- `domain/payment.py::cancel` permits only AUTHORIZED.
- `services/payments.py::_execute_claimed_lifecycle_operation` always inserts
  a ledger entry, including cancellation. Allowing another state alone would
  incorrectly attempt a financial entry for an unpaid cancellation.
- Existing synchronous cancellation tests require the CANCEL ledger entry;
  that behavior must remain unchanged.
- Confirmation processing classifies CANCELLED as `already_resolved` already.
- Receipt acceptance, completion, recovery, and expiry use SQLite writer
  coordination. Cancellation must join the same ordering boundary before
  inspecting receipts or payment state. An in-process lock is not sufficient.
- Existing lifecycle idempotency identifies operation and payment ID and
  preserves a successful response snapshot.

## Decisions for approval

### 1. Accepted confirmation takes priority

Recommended: a committed, matching, on-time pending receipt blocks cancellation.
Return HTTP 409 with proposed code `confirmation_pending` and message
"A payment confirmation is pending. Check the payment status before cancelling."
Do not expose receipt IDs or submitted confirmation values in this response.
Do not complete the receipt as a side effect of cancellation.

Matching means the same reference, amount, and currency. On-time means the
original receipt acceptance time is strictly before expiry. This is the same
protection rule as expiry. Mismatched, late, or unrelated receipts do not block.

Reason: the system has already accepted evidence that may capture the payment.
Reporting cancellation now would make that evidence ineffective. Tradeoff:
failed processing can block cancellation until retry, recovery, or investigation;
there is no automatic worker or administrative override in this slice.

If cancellation commits before receipt admission, cancellation wins. A later
receipt is retained and processed as `already_resolved`, with no capture.

### 2. Deadline does not silently execute expiry

Recommended: an overdue payment still in AWAITING_PAYMENT can be cancelled if
no protecting receipt exists. Cancellation does not implicitly expire it.
Cancellation and explicit expiry compete under the same writer coordination:
the first committed terminal transition wins. The other must re-read state.

Reason: this keeps expiry an explicit operation. Tradeoff: two overdue payments
can end as CANCELLED or EXPIRED depending on operation order. Reports must use
the recorded state, not infer EXPIRED from the clock alone. Rejecting cancellation
at the deadline would be a different policy and requires an explicit decision.

## Shared acceptance rules

1. AWAITING_PAYMENT cancellation returns HTTP 200 and CANCELLED. Authorized,
   captured, and refunded amounts stay zero. No ledger row, including a
   zero-amount CANCEL row, is created.
2. Increment the version once and create exactly one `payment.cancelled`
   outbox event in the transaction with the payment and idempotency snapshot.
   The original creation event remains; cancellation adds one, not one total.
3. Keep the reference, flow, creation time, and expiry as historical metadata.
4. An identical successful cancellation retry returns its original snapshot;
   no additional version, event, ledger row, or idempotency record is created.
5. The same key for a different payment or operation conflicts. A new key for
   an already CANCELLED payment returns the existing invalid-transition 409.
6. Rejected cancellation leaves no committed idempotency claim or other effect.
   Reusing that key can be evaluated again; it is not a cached success.
7. CAPTURED, EXPIRED, and other disallowed states retain invalid-transition
   behavior. Successful replay is resolved before fresh-state rejection.
8. A later confirmation remains independently queryable as `already_resolved`.
   Existing terminal-state precedence applies even if its values mismatch.
9. AUTHORIZED cancellation retains its existing financial behavior and tests.
   Do not introduce a flow-conditional financial invariant.
10. All participants must coordinate before state-dependent decisions. Lock
    admission failure must roll back and return a safe retryable response, not
    raw database errors; exact error mapping is to be verified in implementation.

## Scenarios for approval

These are subcases of CANC-01, not new milestone IDs. Rows may have several
parameterized tests; the row count is not a promised test count.

| Case | Situation | Required evidence | Level |
|---|---|---|---|
| A | Cancel an awaiting JPY or USD payment | 200; version advances once; all balances zero; no ledger; one new cancelled event; metadata preserved | Unit, API, integration |
| B | Confirmation arrives after cancellation | `already_resolved`; diagnostic remains queryable; payment and financial/event counts unchanged | API, integration |
| C | Retry successful cancellation with identical key | Original snapshot and one effect only | API, integration |
| D | Reuse key for another payment or operation | Conflict; both payments and stored snapshot unchanged | API, integration |
| E | New-key cancellation of cancelled, captured, expired, or other invalid state | Invalid transition; no surviving claim or mutation | Unit, API |
| F | Matching on-time receipt committed; processing paused | Cancellation 409 `confirmation_pending`; receipt unchanged; recovery later captures once | API, integration |
| G | Pending amount mismatch, currency mismatch, late receipt, or unrelated receipt | No cancellation protection; retained receipt evidence; later processing follows terminal-state precedence | Integration |
| H | Cancellation owns writer while receipt admission contends | Force overlap; cancellation commits first; confirmation cannot capture | Concurrency |
| I | Receipt owns writer while cancellation contends | Receipt commits first; cancellation observes protection or completed capture; no cancelled event | Concurrency |
| J | Cancellation competes with receipt completion or recovery | Force both ownership orders; protecting receipt prevents cancellation in either order; exactly one capture | Concurrency |
| K | Cancellation competes with expiry on overdue payment | Force each ownership order; cancellation-first means CANCELLED and expiry skips; expiry-first means EXPIRED and cancellation rejects | Concurrency |
| L | Two cancellation requests overlap | Same-key replay produces one success effect; different keys yield one transition and one invalid-transition result | Concurrency |
| M | Failure while committing cancellation event/snapshot | Full rollback including claim; retry succeeds once; no partial payment or financial effects | Integration |
| N | Existing synchronous cancellation and merchant event consumption | Existing CANCEL ledger behavior preserved; new zero-balance cancelled snapshot projects correctly; no duplicate projection effect | Regression, integration |
| O | Deadline boundaries without expiry execution | Before, exactly at, and after deadline remain cancellable without protecting receipt; pending receipt at deadline is late, not protecting | Integration |
| P | Cancellation fails to acquire database writer | Safe retryable failure, no mutation or retained claim; retry after release remains possible | Integration, API |

Concurrency evidence must use file-backed SQLite, distinct physical connections,
and bounded event-controlled checkpoints. A contender must reach admission while
the owner holds its transaction. Sequential calls or sleeps do not prove a race.
Inspect final state, version, balances, ledger, outbox, idempotency, receipt, and
final confirmation records through a fresh session.

## Implementation sequence after approval

1. Add awaiting cancellation to the pure state transition, retaining the shared
   balance constraints and synchronous behavior.
2. Share writer coordination and receipt-protection logic without circular
   service imports. Admit cancellation before its idempotency/state decisions.
3. Skip ledger insertion specifically for unpaid awaiting cancellation; retain
   atomic payment, snapshot, and lifecycle event persistence.
4. Add pending-conflict response, safe lock-failure handling, and contract tests.
5. Force the listed competing orders and rollback failures. Run existing
   confirmation/expiry/recovery, synchronous lifecycle, and projection regressions.
6. Run the full project gate and write plain-English evidence against A–P.
   Update requirements, catalog, and README only to the verified scope.

No UI, new schema, administrative override, background worker, or reconciliation
report extension is proposed here. Existing local reference catalogs stay untouched.

## Owner review

The owner approved the two policies above and scenario coverage before coding.
In particular, cancellation after the deadline is intentionally not the same
thing as cancellation after an EXPIRED transition.
