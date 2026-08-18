# Milestone 4 Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Milestone | 4: Idempotency, concurrency, and failure recovery |
| Status | Complete, recorded after implementation |
| Owner | Sapta Y Husain |
| Related pull request | [PR #3](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/3) |
| Requirements | Idempotency and failure injection in `docs/payment-requirements.md` |
| Closing report | [Milestone 4 quality report](quality-report.md) |

## Documentation note

The project introduced its milestone documentation standard after Milestone 4
was complete. This catalog was reconstructed from the committed requirements,
test plan, implementation, automated tests, and pull request. It does not claim
that the catalog existed before implementation.

## Situation

Payment clients may repeat requests when a response is slow or lost. Two clients
may also update the same payment at nearly the same time. These conditions can
create duplicate charges, excessive refunds, or an uncertain customer result if
the service does not control them.

Milestone 3 proved normal lifecycle behavior. Milestone 4 tested what happens
when requests overlap or when the client cannot see the final result.

## Quality objectives

- Equivalent requests create at most one financial effect.
- A retry returns the original response, not a later payment state.
- An older request cannot overwrite a newer payment result.
- A failure before commit leaves no partial database state.
- A failure after commit is safe to retry with the same key.
- Test-only failure controls are unavailable by default.
- Payment totals remain equal to their ledger evidence.

## Scope

The milestone covers the payment service, HTTP API, SQLAlchemy transactions,
SQLite persistence, idempotency records, payment versions, and ledger entries.

It does not cover real payment providers, distributed databases, multiple
service processes, webhooks, browser journeys, or load testing.

## Design decisions

### Claim the idempotency key first

The service claims a unique key before applying a financial change. If another
equivalent request owns the key, the second request replays the stored result.
If the request content is different, the service returns a conflict.

### Store an immutable response

An idempotency record stores the original payment response. For example, an
authorization retry still returns `AUTHORIZED` version 1 after the payment has
been captured as version 2.

### Use the payment version as an optimistic lock

A database update includes the version that the request originally read. If a
newer request has already changed the version, the older update fails and its
complete transaction is rolled back.

### Inject failures at exact transaction boundaries

Tests can request a timeout before or after commit. This makes recovery tests
repeatable and avoids random network delays. The HTTP control is disabled unless
the application explicitly enables test or demonstration mode.

## Scenario summary

| ID | Business situation | Expected result | Priority | Level | Automated evidence |
|---|---|---|---|---|---|
| IDM-01 | Two equivalent authorizations arrive together | One payment, authorization ledger entry, idempotency record, and response | Critical | Integration | `test_concurrent_equivalent_authorizations_create_one_financial_effect` |
| IDM-02 | Two equivalent captures arrive together | Capture happens once and the version increases once | Critical | Integration | `test_concurrent_equivalent_captures_increment_version_once` |
| IDM-03 | Two equivalent refunds arrive together | One refund entry and one refunded amount | Critical | Integration | `test_concurrent_equivalent_refunds_create_one_refund_entry` |
| CON-01 | Capture competes with cancellation using different keys | The stale operation fails and cannot overwrite the winner | Critical | Integration | `test_optimistic_lock_rejects_stale_competing_transition` |
| CON-02 | Refunds of 700 and 600 compete against a captured amount of 1,000 | Refunded funds never exceed captured funds | Critical | Integration | `test_competing_refunds_cannot_exceed_captured_amount` |
| RPL-01 | Authorization is replayed after capture | Retry returns the original authorization snapshot | High | Integration | `test_original_authorization_snapshot_survives_later_state_changes` |
| FT-01 | Authorization times out before commit | No payment, ledger, or idempotency record remains | Critical | Integration | `test_timeout_before_commit_rolls_back_and_retry_succeeds_fresh` |
| FT-02 | Client retries after the pre-commit timeout | Retry executes freshly and succeeds once | Critical | Integration | Same test as `FT-01` |
| FT-03 | Invalid authorization fails after claiming its key | The incomplete key claim is rolled back | High | Integration | `test_invalid_authorization_rolls_back_its_idempotency_claim` |
| FT-04 | Authorization commits but the response times out | Retry replays the committed result without a duplicate | Critical | Integration | `test_timeout_after_commit_retries_original_result_without_duplicate` |
| LED-01 | Refund commits before a timeout and is then retried | Payment totals still equal authorization, capture, and refund ledger totals | Critical | Integration | `test_ledger_totals_match_payment_after_recovered_refund_timeout` |
| API-01 | A normal application receives a failure-control header | Request is rejected and no payment is created | High | API | `test_failure_control_is_rejected_when_not_explicitly_enabled` |
| API-02 | Pre-commit timeout occurs through HTTP | API returns a timeout, leaves no effect, and accepts a fresh retry | Critical | API | `test_pre_commit_timeout_leaves_no_effect_and_retry_is_fresh` |
| API-03 | Post-commit timeout occurs through HTTP | API returns an uncertain result and the same-key retry safely replays it | Critical | API | `test_post_commit_timeout_recovers_original_response_without_duplicate` |
| API-04 | Capture commits before an HTTP timeout | Retry returns one captured result and one capture ledger entry | Critical | API | `test_post_commit_capture_timeout_is_safe_to_retry` |
| API-05 | Authorization HTTP response is replayed after capture | Replay returns the original body while normal retrieval returns current state | High | API | `test_authorization_replay_returns_original_http_response_after_capture` |

## Detailed centerpiece scenario

### API-03: response is lost after commit

#### Business risk

The customer may see a timeout even though the payment service saved the
authorization. If the client sends a new request, the customer could be charged
twice. The client must repeat the request with the same idempotency key.

#### Preconditions

- The application uses an isolated test database.
- Failure injection is explicitly enabled.
- The client has a valid authorization request and idempotency key.

#### Steps

1. Send the authorization with the `after_commit` failure point.
2. Confirm that the API returns `504 payment_timeout`.
3. Send the same request with the same idempotency key.
4. Retrieve the payment ledger.

#### Expected result

- The retry returns the original `AUTHORIZED` version 1 response.
- The response marks the request as an idempotent replay.
- The database contains one payment and one authorization ledger entry.
- No second financial effect is created.

## Exit criteria

- All listed scenarios pass from a clean checkout.
- Payment and ledger invariants remain true.
- Ruff lint and formatting checks pass.
- Branch-aware coverage remains above the 85% release gate.
- Python 3.12 and 3.14 GitHub Actions jobs pass.
- Any genuine defect found during the milestone has regression coverage.
