# E2 awaiting cancellation: quality report

Status: Local gate passed; PR CI pending at report creation.
Date: 2026-09-11. Branch: `codex/e2-awaiting-cancellation`.
Scope: [approved CANC-01 review, A–P](cancellation-review.md).

## Business result

A merchant can cancel an unpaid awaiting request without creating a financial
ledger entry. A committed matching on-time confirmation blocks cancellation,
even if processing is delayed. This prevents the system from reporting
cancellation while accepted payment evidence is waiting to be applied.

Cancellation does not execute expiry implicitly. Without a protecting receipt,
an overdue awaiting request remains cancellable. Cancellation and explicit
expiry use the same database ordering: the first committed terminal transition
wins. This is the approved simulator policy, not a provider compatibility claim.

## Implementation and tradeoffs

The pure cancellation transition now accepts AWAITING_PAYMENT as well as
AUTHORIZED. The service skips ledger insertion only for awaiting cancellation;
authorized cancellation keeps its existing CANCEL ledger entry. The shared
financial invariant is unchanged.

`services/coordination.py` shares SQLite writer admission and the protecting
receipt predicate between cancellation, confirmation, and expiry. Cancellation
acquires admission before idempotency and payment-state decisions. Success
commits payment, version, outbox event, and replay snapshot together. Rejection
or pre-commit failure retains no cancellation claim. A post-commit timeout can
be retried with the original key to obtain its saved response.

Pending protection returns 409 `confirmation_pending`. Database failures return
503 `cancellation_unavailable` without database details. Later confirmations
remain queryable internally as `already_resolved`, without capturing funds.

All cancellation requests now use SQLite coordination, including synchronous
ones. Writer serialization limits throughput. This does not establish other
database-engine or distributed correctness. Service calls require dedicated
clean sessions. No schema change, background worker, or cancellation override
was added. A permanently failing protecting receipt requires investigation;
cancellation does not automatically clear it.

## Evidence map

| Cases | Executed evidence |
|---|---|
| A | Pure-state test and JPY/USD HTTP journeys prove CANCELLED, preserved metadata and zero balances; fresh-session integration assertions prove version, no ledger, one added event, and idempotency count |
| B | Signed confirmation after cancellation returns a safe acknowledgement; internal diagnostic reports already_resolved; payment remains unchanged |
| C/D | Identical-key replay returns the original snapshot; key reuse for another payment or capture conflicts |
| E | Existing disallowed lifecycle regressions, new-key repeated cancellation, expiry-first rejection, and a stale-session cancellation test retain terminal state |
| F | Pending receipt causes explicit API 409, no retained cancellation claim, and subsequent recovery captures once |
| G | Pending amount/currency mismatch, late, and unknown-reference receipts do not block cancellation; final diagnostics follow existing terminal-state precedence |
| H/I | Forced cancellation-first and receipt-first admission show cancellation winning or pending protection respectively |
| J | Both ownership orders against completion and recovery retain one capture and no cancellation effect |
| K | Forced cancellation/expiry ownership orders yield exactly one terminal transition |
| L | Overlapping same-key and different-key cancellation requests produce one transition, with replay or invalid-transition response respectively |
| M | Injected outbox failure and before/after-commit failure controls prove rollback or replay at the correct boundary |
| N | Existing synchronous CANCEL ledger regressions pass; signed cancelled snapshot and duplicate deliveries update the merchant projection without financial amounts |
| O | Injected cancellation time before, at, and after expiry does not implicitly expire; a receipt accepted at expiry does not protect |
| P | Real held-writer timeout proves no committed cancellation effect; separate HTTP fault injection verifies safe 503 and successful retry |

New integration cases live in `tests/integration/test_confirmation_races.py`;
HTTP cases are in `tests/api/test_payment_confirmations.py`. Races use distinct
physical connections, file-backed SQLite, and bounded event checkpoints. A
contender must attempt admission while the owner holds the transaction. No
sleep is used to arrange the ordering. Database state is checked from a fresh
session after competing calls finish.

## Test adjustment found during the full gate

An existing stale-cancellation test expected an optimistic-lock error. With
writer admission and refreshed state, cancellation instead rejects CAPTURED
before attempting an update. The optimistic-lock test now uses stale capture
after winning cancellation, so that protection is still exercised. A separate
test proves stale cancellation reloads the captured state and changes nothing.
The old assertion was not simply removed.

## Local verification

- 386 Python tests passed; branch-aware coverage 86.05% against the 85% gate.
- 45 Node tests passed; TypeScript check passed.
- 11 Chromium Cucumber scenarios and 100 steps passed.
- Ruff lint and formatting passed.
- PR CI results will be recorded in the PR before merging.

## Remaining work

Confirmation reconciliation reporting, English/Japanese asynchronous messaging,
exploratory closeout, and the final E2 report remain separate slices. Existing
reports remain historical evidence, not claims that those slices are complete.
