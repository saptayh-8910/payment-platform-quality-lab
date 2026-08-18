# Milestone 4 Quality Report

## Document information

| Field | Value |
|---|---|
| Milestone | 4: Idempotency, concurrency, and failure recovery |
| Result | Proceed with documented limitations |
| Feature commit | `83c06c7` |
| Merge commit | `81d9fad` |
| Pull request | [PR #3](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/3) |
| CI run | [GitHub Actions run 32092661866](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32092661866) |
| Execution date | 2026-08-18 |

## Executive summary

Milestone 4 met its quality objectives for this simulator. Equivalent concurrent
requests created one financial effect. Stale competing requests could not
overwrite a newer payment result. Pre-commit failures rolled back, and
post-commit failures were safe to retry with the same idempotency key.

The final suite contained 104 tests and reached 99.16% branch-aware coverage.
GitHub Actions passed on Python 3.12 and 3.14. One genuine transaction rollback
defect was found during implementation, fixed, and covered by regression tests.

The result supports progress to webhook and reconciliation testing. It does not
prove behavior on a distributed production database or under sustained load.

## Situation

Normal API tests cannot show whether a payment remains safe when two requests
overlap or when a response is lost. These are important payment risks because a
client may retry without knowing whether the first request committed.

The previous service checked idempotency in sequence and returned the current
payment record on replay. It also increased the payment version without using
that version to reject stale database updates.

## Why this risk mattered

An unsafe retry can create a duplicate charge or refund. A stale update can
replace newer payment state. Returning a changed response for an old request can
also confuse a client that expects the original result.

These failures affect financial correctness, customer trust, and incident
investigation. They were treated as critical or high priority.

## Quality approach

The milestone combined API and database integration tests:

- Real HTTP tests checked public status codes, replay headers, and response
  bodies.
- File-backed SQLite tests used independent sessions for concurrent requests.
- Synchronization barriers made equivalent requests start together without
  timing sleeps.
- Stale sessions proved that the database version rejected an older update.
- Deterministic failure points tested both sides of the transaction commit.
- Assertions checked payment rows, ledger entries, idempotency records, response
  snapshots, and versions.

A successful HTTP response was not treated as enough evidence. Each critical
test also checked the stored financial result.

## Important decisions

### Unique idempotency claim

The service claims a key before changing payment state. This gives concurrent
equivalent requests one owner and one stored outcome.

### Immutable response snapshot

The original response is stored with the idempotency record. This prevents a
later payment change from changing the meaning of an earlier retry.

### Optimistic locking

The payment version is included in database updates. An old request receives a
concurrency conflict instead of silently replacing newer state.

### Controlled failure injection

The simulator supports `before_commit` and `after_commit` timeouts only when an
application instance explicitly enables them. Normal application instances
reject the control.

## Execution evidence

| Evidence | Result |
|---|---|
| Full automated suite | 104 passed |
| New focused reliability tests | 15 passed in the final suite |
| Branch-aware coverage | 99.16% |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Python 3.12 CI | Passed |
| Python 3.14 CI | Passed |
| Working tree whitespace check | Passed |

The focused scenarios are mapped in the [Milestone 4 scenario catalog](scenario-catalog.md).

## Defects and observations

One genuine defect was observed while the claim-first transaction flow was being
implemented. An invalid lifecycle transition could leave an idempotency claim
inside a caller-managed database session. The API request wrapper normally
rolled back the session, but direct service use could retain the incomplete
transaction.

The service now rolls back every claimed operation when validation or persistence
fails. Existing invalid-transition coverage and a new invalid-authorization
regression test confirm that no claim remains. See
[DEF-002](../../../defects/DEF-002-idempotency-claim-rollback.md).

## Limitations

- SQLite is useful for deterministic local tests but does not represent every
  production database locking behavior.
- Concurrency tests run in one process with separate database sessions.
- The simulator does not call a real payment provider.
- Failure injection models exact transaction boundaries, not every network or
  infrastructure failure.
- The milestone does not provide webhook, browser, reconciliation, or load-test
  evidence.
- The project does not claim production readiness or PCI DSS compliance.

## Release recommendation

Proceed to Milestone 5 with the stated limitations. The evidence is sufficient
for the simulator's idempotency and failure-recovery requirements. Webhook
delivery and reconciliation remain necessary before the payment reliability
story is complete.

## Next quality risks

- A webhook may be delivered more than once.
- Events may arrive in a different order from their payment operations.
- A consumer may process an event before the producer sees its acknowledgement.
- Payment, ledger, webhook projection, and settlement data may disagree.

These risks are covered by the draft
[Milestone 5 scenario catalog](../m5-webhooks-reconciliation/scenario-catalog.md).
