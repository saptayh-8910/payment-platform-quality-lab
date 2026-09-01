# Enhancement 1 Detailed Decline Outcomes Quality Report

## Document information

| Field | Value |
|---|---|
| Enhancement | 1: Detailed declined-payment outcomes |
| Result | Proceed within the declared simulator boundary |
| Backend commit | `0b84b29` |
| Checkout and exploratory commit | `e73429f` |
| Pull request | Pending |
| CI run | Pending |
| Local execution date | 2026-09-02 |

## Executive summary

Enhancement 1 is implemented and passed its local release gates. The simulator
now distinguishes six provider-neutral decline reasons while keeping one final
`DECLINED` lifecycle state. Every reason is stored, returned, replayed, and
included in the declined webhook snapshot without creating a financial ledger
effect.

The checkout maps each reason to owner-approved English and Japanese guidance.
The visible page does not show the normalized code or submitted simulator token.
Browser automation samples insufficient funds in both languages, and a focused
exploratory session checked the same result at desktop and mobile widths.

One genuine database defect was found during implementation. The first check
constraint allowed a declined row with a null reason because SQL treats a null
comparison as unknown. [DEF-007](../../../defects/DEF-007-null-decline-reason-constraint.md)
records the cause, correction, and regression evidence. The defect was fixed
before this report.

The recommendation is to proceed. CI evidence must still run on the pull
request before merge.

## Situation

The earlier simulator had one generic decline control. It proved that a decline
created no ledger entry, but every negative outcome looked the same. The API,
stored payment, webhook consumer, and checkout could not distinguish an expired
payment method from insufficient funds or failed verification.

This created two quality problems. A customer could receive guidance that did
not match the situation, and an investigator could not confirm that every
system view preserved the original reason.

## Why the risk mattered

Detailed negative paths touch more than the result page. A change could:

- create an authorization ledger entry for a declined attempt;
- lose or change the reason during storage or retry;
- return an earlier result after conflicting idempotency-key reuse;
- make the merchant projection disagree with the payment;
- expose the submitted test token in retained evidence; or
- show an internal code instead of useful customer guidance.

The tests therefore checked the complete path from deterministic input through
financial storage, event delivery, customer presentation, and retained
evidence.

## Implemented behavior

| Synthetic control | Stored reason | Financial effect |
|---|---|---|
| `tok_declined_insufficient_funds` | `insufficient_funds` | None |
| `tok_declined_limit_exceeded` | `limit_exceeded` | None |
| `tok_declined_expired` | `expired_payment_method` | None |
| `tok_declined_verification` | `verification_failed` | None |
| `tok_declined_invalid` | `invalid_payment_method` | None |
| `tok_declined_unknown` | `unknown` | None |

The legacy `tok_declined` control remains a backward-compatible alias for
`unknown`. It is accepted through the API but is not displayed as a checkout
option.

## Quality approach

- Domain tests prove that every token maps to one recognized reason and that an
  approval has no reason.
- API tests prove creation, retrieval, exact replay, conflict responses, zero
  balances, and token-free responses.
- Database integration tests compare the payment, immutable idempotent response
  snapshot, ledger count, and webhook payload.
- Direct invalid writes prove that the database rejects missing, unknown, or
  status-incompatible reasons.
- Webhook tests deliver a detailed decline and verify the same reason in the
  merchant projection.
- Node tests check every reason in English and Japanese and verify the safe
  fallback for a future reason.
- Cucumber-JS and Playwright check customer-visible guidance, privacy, and
  request count in Chromium.
- The trace sanitizer test proves that detailed submitted tokens do not survive
  in a retained browser trace.
- Exploratory testing checks communication, focus, language switching, and
  responsive presentation beyond exact text assertions.

## Important decisions

| Decision | Reason |
|---|---|
| Keep one `DECLINED` state | Status explains what happened; reason explains why |
| Store normalized reasons | A stable safe value supports retrieval and event comparison without storing a raw external response |
| Keep `tok_declined` as an alias for `unknown` | Existing API examples and tests continue to work while new work uses detailed controls |
| Return the reason through the payment API | The simulator has no authenticated support portal; the checkout maps the code instead of displaying it |
| Test every message mapping but sample one reason in Chromium | This proves complete mapping coverage without repeating six almost identical slow journeys |
| Scope no-auto-resubmission to the checkout | Backend idempotency cannot block intentionally separate requests with new keys |

## Execution evidence

| Evidence | Result |
|---|---|
| Full Python suite | 264 passed |
| Branch-aware Python coverage | 96.57%; required minimum 85% |
| Node unit suite | 30 passed, including 13 decline-guidance tests |
| TypeScript check | Passed |
| Cucumber-JS and Chromium | 10 scenarios and 81 steps passed |
| Ruff formatting and lint | Passed |
| Local Python | 3.14.7 |
| Local Node | 24.12.0 |
| Local Playwright | 1.62.1 |
| Pull-request CI | Pending; required before merge |

Repeatable commands:

```bash
python -m pytest
npm run test:browser
ruff check src tests scripts
```

The approved basis is the [scenario catalog](scenario-catalog.md). The focused
exploratory evidence is in the [session record](exploratory-session.md).

## Scenario result

| Scenario group | Result | Main evidence |
|---|---|---|
| `DECL-01` to `DECL-06` | Pass | Domain, API, and cross-record parameterized tests |
| `FIN-01` | Pass | Zero balances and zero ledger rows for every detailed decline |
| `RET-01` | Pass | Created and retrieved payment responses match |
| `IDM-01` | Pass | Exact replay returns the complete original response and one event |
| `IDM-02` | Pass | Changed token, amount, currency, or reference returns `409` and changes nothing |
| `WH-01` | Pass | One sanitized version-one declined event contains the normalized reason |
| `WH-02` | Pass | Delivered event creates a projection with the same reason |
| `LOC-01` | Pass | All six reasons have nonempty English and Japanese guidance |
| `LOC-02` | Pass | Insufficient-funds journey passes in English and Japanese Chromium scenarios |
| `UI-01` | Pass | Request count stays at one while the customer takes no action |
| `PRIV-01` | Pass | API, snapshots, events, storage, and sanitized traces contain no submitted token |

## Defects and observations

### DEF-007: null decline reason passed the database check

The new integration test exposed a mistake in the first constraint. Adding an
explicit `decline_reason IS NOT NULL` condition closed the gap. Three invalid
status-and-reason combinations now fail at the database boundary.

No other product defect was found. One test assertion initially confused a
successful delivery attempt outcome with the final event status. The assertion
was corrected; this was a test vocabulary mistake, not a product defect.

## Exploratory evidence

The session reviewed insufficient-funds guidance in English and Japanese. It
also switched language on the completed result and checked a 390 × 844 viewport.

Observed results:

- the same payment ID, reference, amount, and status remained stable after the
  language switch;
- the guidance gave a clear next action in both languages;
- the normalized code did not appear in the visible result;
- focus moved to the result panel;
- no horizontal overflow appeared at the mobile width; and
- the result remained stable without another customer action.

No exploratory defect was found.

## Limitations

- All values and outcomes are synthetic. No real credentials, provider API, or
  remote sandbox was used.
- The database evidence uses fresh SQLite schemas. This repository does not
  provide a production migration for an older persistent `payment_lab.db`.
- Browser automation runs in Chromium. Firefox, WebKit, native mobile, and
  complete assistive-technology testing remain outside scope.
- Interactive exploration sampled insufficient funds. Unit tests cover all
  message mappings, but the six complete browser journeys were not repeated.
- Japanese guidance received owner review but not professional translation
  certification.
- Shared webhook retry and out-of-order behavior was not repeated for every
  reason because Milestone 5 already covers that mechanism.
- A normalized reason is not a raw external response and cannot prove how a
  real provider would classify every decline.

## Release recommendation

Proceed within the declared simulator boundary after the pull-request CI gate
passes. The evidence supports the approved behavior: each decline has one safe
reason, no financial effect, stable retry behavior, consistent webhook
projection, and useful localized guidance.

## Next quality risks

Enhancement 2 will add asynchronous payment confirmation. Its catalog remains a
local review reference and must not be implemented until this enhancement is
merged and closed. The next risks are durable confirmation identity, expiry,
late arrival, concurrency, reconciliation, and customer messaging for an
awaiting-payment state.
