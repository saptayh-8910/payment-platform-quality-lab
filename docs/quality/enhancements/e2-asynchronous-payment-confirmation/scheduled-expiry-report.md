# Enhancement 2 Scheduled Expiry Report

## Document information

| Field | Value |
|---|---|
| Enhancement | 2: Asynchronous payment confirmation |
| Slice | Scheduled expiry for unconfirmed delayed payments |
| Result | Ready to merge; full pull-request CI passed |
| Branch | `codex/e2-scheduled-expiry` |
| Pull request | [#23](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/23) |
| Local execution date | 2026-09-10 |

## Executive summary

The service can now close a delayed payment when no confirmation arrives before
its deadline. The internal `expire_due_payments(now)` operation finds overdue
payments that are still waiting and changes each one to `EXPIRED`.

Expiry does not report money that was never confirmed. It creates no ledger
entry and leaves authorized, captured, and refunded balances unchanged at zero.
It creates one `payment.expired` event so downstream systems can observe the
final status.

## Business risk

Without an explicit expiry operation, a payment can remain
`AWAITING_PAYMENT` forever when no confirmation arrives. That can mislead a
customer, merchant, or support user into believing the payment is still active.

A careless scheduler creates different risks. It could expire a payment before
the deadline, process the same payment twice, create duplicate events, or leave
part of a batch changed after a failure. This slice tests each of those risks.

## Implemented controls

- The operation accepts a trusted, timezone-aware UTC time.
- It selects only `AWAITING_PAYMENT` records with `expires_at <= now`.
- The exact deadline is included. One microsecond before it is not.
- The default batch limit is 100 and the accepted range is 1 to 1,000.
- Candidates are ordered by expiry time and then payment ID.
- The scheduler and late-confirmation path call one shared expiry transition.
- Each transition changes the payment version once and creates one
  `payment.expired` event.
- No ledger entry or financial balance change is created.
- A repeated run does not select an already expired payment.
- One bounded batch commits as a unit. An event failure rolls back every
  payment and event in that batch.

## Scenario results

| `CONF-03` case | Result | Main evidence |
|---|---|---|
| Before deadline | Passed | Payment remained awaiting with version 1 and only its creation event |
| Exact deadline | Passed | Payment expired once because `expires_at <= now` |
| After deadline | Passed | Payment expired once with the supplied trusted time |
| Repeated execution | Passed | Second run returned no payment and created no second event |
| Bounded mixed batch | Passed | Earliest due records were processed first; future record remained awaiting |
| Resolved payment exclusion | Passed | Captured payment was not selected or changed |
| Event failure | Passed | Complete two-payment batch rolled back |
| Invalid batch limits | Passed | Zero and more than 1,000 were rejected |
| Naive time | Passed | Ambiguous datetime was rejected before selection |
| Shared late path regression | Passed | Existing late-confirmation tests still produced one expiry transition and event |

## Automated evidence

| Evidence | Result |
|---|---|
| Complete Python suite | 328 passed |
| Branch-aware coverage | 86.58%; required minimum 85% |
| Scheduled-expiry unit and integration tests | Passed |
| Existing confirmation regression tests | Passed |
| Node unit suite | 45 passed |
| TypeScript check | Passed |
| Cucumber-JS and Chromium regression | 11 scenarios and 100 steps passed |
| Ruff lint and formatting | Passed |
| Git diff check | Passed |
| GitHub Actions pull-request gate | Six checks passed across Python, Chromium, and performance workflows |

## Transaction and failure evidence

The rollback test creates two overdue payments and forces creation of the second
expiry event to fail. The first payment and event have already been staged at
that point. The operation rolls the entire transaction back. Both payments
remain awaiting, and neither expiry event exists.

This is a deliberate bounded-batch policy. It gives one clear result: either
the selected batch is complete or none of it is. A later production design
could isolate failures per payment, but that would require a separate result
and retry contract.

## Limitations and remaining risk

- The operation is a service function. This repository does not configure a
  production scheduler or infrastructure deployment.
- A batch is limited, but this slice does not measure expiry throughput.
- Simultaneous confirmation and expiry are not claimed as safe yet. `RACE-01`
  must force both processing orders and prove the durable receipt-time rule.
- Cancellation from `AWAITING_PAYMENT` remains unimplemented.
- Reconciliation does not yet report confirmation outcomes and anomaly totals.
- English and Japanese awaiting and expired guidance remains unimplemented.

## Recommendation

Proceed to merge `CONF-03`. The local and CI evidence supports the
deadline rule, zero financial effect, one lifecycle event, repeat safety,
deterministic bounded selection, and atomic rollback.

Do not describe the full asynchronous-confirmation enhancement as complete.
The forced race is the next critical slice because sequential tests cannot
prove which operation wins under concurrency.

## Next review

Review `RACE-01`: confirmation and scheduled expiry acting on the same payment
before, at, and after the deadline.
