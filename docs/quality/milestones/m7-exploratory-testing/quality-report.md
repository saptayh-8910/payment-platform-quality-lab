# Milestone 7 Quality Report

## Document information

| Field | Value |
|---|---|
| Milestone | 7: Structured exploratory testing and defect evidence |
| Result | Proceed to Milestone 8 with documented limitations |
| Exploratory commit | `5cde81041e07a78ad898c016f3c42152912121b5` |
| Pull request | Current Milestone 7 pull request; link added after creation |
| Execution date | 2026-08-21 |
| Executed session | [M7-S01](session-record.md) |

## Executive summary

Milestone 7 challenged the checkout outside its eight scripted acceptance
journeys. The session combined refresh, retry, repeated input, server pauses,
offline behavior, language changes, stale backend data, mobile validation, and
cross-layer investigation.

The work found one genuine High defect. Refresh removed the uncertain-payment
message and safe Retry action after the payment had committed but the response
was lost. The server prevented a duplicate effect, but the browser no longer
helped the customer recover the original result.

The defect was reproduced in Japanese and English, documented as
[DEF-006](../../../defects/DEF-006-uncertain-payment-lost-after-refresh.md),
fixed, and added to the critical Cucumber regression journey. The uncertain
state now survives refresh. Retry uses the original details and idempotency key,
then returns the same committed payment with one ledger and webhook effect.

The session also confirmed agreement between the visible checkout, payment API,
immutable ledger, webhook projection, and reconciliation report. Generated
coverage evidence was improved so it no longer needs an absolute workstation
path.

The result supports progress to the performance milestone. It does not prove
cross-browser behavior, native-mobile quality, complete accessibility, every
damaged browser state, or every possible malformed network response.

## Situation

Milestone 6 proved selected customer journeys with repeatable automation. Those
scenarios were designed from known risks and expected results. They did not show
what would happen when several unusual actions were combined in a new order.

This milestone used a charter because the next useful action depended on the
previous observation. For example, an honest uncertain message led to a refresh,
the refresh exposed a hidden stale key, and that key led to a different-details
conflict. A fixed script would not have followed this chain as naturally.

## Quality approach

The session used four connected lenses:

- A customer lens checked whether messages and recovery actions were clear.
- A financial lens checked whether one intended action created one effect.
- A support lens reconstructed the result across payment, ledger, webhook, and
  reconciliation records.
- A privacy lens checked collected fields, URLs, visible errors, browser state,
  and generated artifacts.

The session record contains timestamps, exact environment details, combinations,
classification decisions, evidence, and truthful gaps. Temporary databases and
browser images were removed because the written and automated evidence is enough
to reproduce the important behavior.

## Main finding and decision

### DEF-006: uncertain recovery was lost after refresh

This was a High defect because it blocked a safe customer recovery journey. It
was not Critical because payment, ledger, idempotency, and webhook records stayed
correct and no duplicate financial effect occurred.

The fix makes a deliberate privacy and reliability trade-off. While a request
is uncertain, the current browser tab retains only the active idempotency key
and a minimal synthetic retry packet. The packet contains the synthetic
reference, integer amount, currency, and a neutral approval or decline choice.
It contains no real payment data, identity, signing secret, or raw API token.

The packet is cleared after a final response or New checkout. A completed result
keeps only the payment ID needed for refresh. Invalid or incomplete recovery
data is discarded.

## Regression evidence

The existing critical Japanese uncertain-payment scenario was extended instead
of adding a second overlapping test. Its sequence is now:

1. Submit a valid Japanese JPY payment.
2. Commit the payment and lose the first response.
3. Confirm the honest uncertain message and Retry action.
4. Refresh before retry.
5. Confirm that the uncertain Japanese state still exists.
6. Retry with the same request and idempotency key.
7. Confirm the original payment ID and completed result.
8. Refresh again and confirm one ledger and webhook effect.

This keeps the scenario business-readable while proving the browser, API,
idempotency, database, and financial result together.

## Exploratory evidence

| Area | Result |
|---|---|
| Completed and restored result | English and Japanese IDs, references, amounts, and statuses stayed consistent |
| Repetition during processing | The disabled action and request guard allowed one payment request and one effect |
| Offline before request | The message stayed uncertain; retry after restart created one effect |
| Stale completed-result ID | Localized missing-result guidance and New checkout recovery worked |
| Response loss after commit | DEF-006 reproduced twice, then passed after the fix |
| Mobile validation and success | Focus, language, wrapping, result state, and 390-pixel layout behaved correctly |
| Unicode boundary | A 64-code-point reference succeeded; input beyond the native limit remains an explicit question |
| Cross-layer investigation | Payment, ledger, webhook projection, and reconciliation report agreed |
| Artifact review | No secret or full failure header appeared; coverage source paths were made relative |

## Final automated evidence

The complete local gate passed after the fix. The browser scenario now contains
two additional recovery steps. Pull-request CI remains the publication gate.

| Evidence | Final result |
|---|---|
| Full pytest suite | 199 passed |
| Branch-aware Python coverage | 98.40% |
| Node money tests | 17 passed |
| TypeScript type checking | Passed |
| Cucumber acceptance | 8 scenarios and 60 steps passed |
| Chromium browser gate | Passed |
| Ruff lint and formatting | Passed |
| Working tree whitespace check | Passed |
| Pull-request CI | Pending pull-request creation |

## Observations that remain open

- The exact product meaning of the 64-character reference limit for complex
  Unicode input is not explicitly agreed. The code and API currently count
  Unicode code points.
- Keyboard focus moved to the validation summary, but the session did not obtain
  reliable evidence for activating its field link with every keyboard method.
- Malformed JSON, direct 5xx routing, Firefox, WebKit, native mobile, and full
  assistive-technology behavior were not covered by this session.

These are recorded limitations, not passed tests and not confirmed defects.

## Limitations

- Chromium is the only required browser.
- The mobile viewport represents responsive web behavior, not a native app.
- Japanese copy has not received professional translation certification.
- This is a focused keyboard and semantic review, not WCAG certification.
- SQLite and one local FastAPI process do not represent distributed production
  infrastructure.
- Controlled response loss and offline behavior represent selected failure
  boundaries only.
- All data and outcomes are synthetic. The project processes no real payments.
- The short session used deterministic controls and closed after all critical
  threads were touched; it did not consume the full 90-minute maximum.

## Release recommendation

Proceed to Milestone 8 after the complete local gate and pull-request CI pass.
DEF-006 has been resolved with business-readable regression evidence. No
Critical or High finding remains open for the declared Milestone 7 scope.

The next milestone should measure performance and reliability under documented
load without reopening the completed browser scope unless a listed limitation
becomes a release requirement.
