# Enhancement 1 Detailed Decline Outcomes Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Enhancement | 1: Detailed declined-payment outcomes |
| Status | Approved plan; no scenario in this document is passed evidence |
| Owner | Sapta Y Husain |
| Review | Scenario decisions reviewed before repository authoring on 2026-09-01 |
| Planned delivery | Separate catalog, implementation, and closing-evidence pull requests |
| Test basis | [Payment requirements](../../../payment-requirements.md), [risk-based test plan](../../../test-plan.md), and completed reliability, webhook, browser, and exploratory evidence |
| Closing evidence | Created only after implementation and execution |

## Executive summary

The simulator currently represents every declined authorization with one
synthetic outcome. This proves the basic negative path, but it cannot show
whether different decline reasons are stored, returned, localized, retried, and
investigated safely.

This enhancement will add six deterministic, provider-neutral decline reasons.
The payment lifecycle will keep one final `DECLINED` state. A separate normalized
reason will explain why the payment was declined without making the state
machine larger.

The main risk is not only an unclear customer message. A change could create a
ledger effect for a decline, lose the reason during retrieval, return a previous
payment for a conflicting idempotency request, expose a test token, or publish
an incomplete webhook event.

This catalog records approved behavior and planned evidence. It does not claim
that the scenarios have been implemented or passed.

## Situation

The existing simulator accepts `tok_approved` and `tok_declined`. The declined
outcome creates a stored payment and webhook event without a financial ledger
entry. The checkout shows localized declined guidance.

All declined attempts currently look the same. A customer cannot receive a
specific next action, and an investigator cannot distinguish insufficient funds
from expired information or failed verification. Adding detailed reasons
changes the domain record, API response, idempotency fingerprint, webhook
payload, checkout localization, and privacy evidence together.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| A decline creates a financial ledger effect | Financial totals report money that was never authorized | Critical |
| A conflicting request receives an earlier result | A client may believe changed payment details were processed | Critical |
| The stored reason is lost or changes during retrieval | Support cannot explain the original result reliably | High |
| A customer sees an internal reason code | The result is confusing and localization is incomplete | High |
| A webhook omits or changes the normalized reason | A downstream merchant view disagrees with the payment record | High |
| A token or sensitive value reaches retained evidence | Test reports or integration payloads expose unsafe input | High |
| The checkout resubmits an unchanged decline automatically | Repeated attempts create noise and confuse the customer | Medium |
| An unknown reason breaks the result page | A future reason prevents safe customer recovery | Medium |

## Scope

### Included

- Six deterministic decline controls and normalized reason values.
- One final `DECLINED` lifecycle state with a separate reason.
- New authorization and stored-payment retrieval contracts.
- Exact persistence, idempotency, ledger, and webhook checks.
- Same-key identical retry and same-key conflicting-request behavior.
- Complete English and Japanese message-map tests.
- Representative browser coverage using the same reason in both languages.
- Exploratory review of guidance and automatic resubmission behavior.
- Privacy checks across API, event, browser, log, screenshot, and report
  surfaces.

### Outside this enhancement

- Real payment credentials, customer data, external APIs, and remote sandboxes.
- Card-number parsing, card-brand routing, or network-specific behavior.
- Storing raw external error responses.
- A new support portal, diagnostic HTTP endpoint, role system, or
  authentication design.
- Repeating the complete webhook retry, duplicate-delivery, and out-of-order
  suite for every reason. The shared delivery mechanism already has dedicated
  Milestone 5 evidence.
- Automatic retry policy for business declines.
- Customer authentication challenges and interrupted redirect behavior. They
  require a separate scenario review.
- Performance, stress, and soak testing for each decline reason.

## Approved behavior

### Status and reason

`DECLINED` remains the lifecycle state. One provider-neutral reason is stored
separately:

| Synthetic control | Normalized reason | Intended customer action |
|---|---|---|
| `tok_declined_insufficient_funds` | `insufficient_funds` | Use another payment method or resolve the available-funds problem |
| `tok_declined_limit_exceeded` | `limit_exceeded` | Use another method or a permitted amount |
| `tok_declined_expired` | `expired_payment_method` | Update the payment method |
| `tok_declined_verification` | `verification_failed` | Check the submitted payment information |
| `tok_declined_invalid` | `invalid_payment_method` | Check or replace the payment method |
| `tok_declined_unknown` | `unknown` | Show safe generic guidance without exposing internal detail |

The controls are synthetic strings, not credentials. The mapping belongs at
the authorization boundary. Domain, persistence, webhook, and UI behavior will
use the normalized reason rather than interpreting token strings again.

### API and persistence contract

- A new declined attempt returns HTTP `201`, payment status `DECLINED`, and its
  normalized `decline_reason`.
- An identical idempotent replay returns HTTP `200`, the replay header, and the
  original payment ID, status, reason, timestamps, and financial values.
- Retrieving the stored payment returns the same normalized reason.
- An authorized payment has no decline reason.
- A declined payment must have one recognized normalized reason. `unknown` is a
  recognized safe fallback, not a missing value.
- A decline stores zero authorized, captured, and refunded minor units.
- A decline creates no financial ledger entry.

The API reason is a stable machine-readable value. It is not a raw external
message and is safe for a client to map. The checkout must never insert this
code directly into customer-facing text.

### Idempotency contract

Idempotency has two different behaviors:

1. Same key and identical request: return the original result without another
   payment, ledger entry, idempotency record, or webhook event.
2. Same key and changed request: return HTTP `409` with the existing
   `idempotency_conflict` contract. Do not return the original payment as if the
   changed request succeeded, and do not create a new payment.

Conflicting-request coverage will change each fingerprinted input separately:

- payment token;
- amount;
- currency; and
- merchant reference.

### Customer presentation

- Before UI implementation, every reason receives reviewed English and
  Japanese guidance.
- The same normalized reason selects equivalent customer action in both
  languages.
- The visible checkout does not show snake-case codes or submitted tokens.
- `unknown` uses a safe generic message and leaves the customer a clear next
  action.
- Preventing automatic resubmission is a checkout responsibility. The backend
  does not claim to throttle separate requests that use new keys.

### Webhook behavior

- Every new declined payment creates one version-one `payment.declined` event in
  the same transaction.
- The full-snapshot payload contains the normalized reason and final financial
  values.
- The payload contains no submitted payment token or customer data.
- One representative declined event will pass through the existing delivery and
  consumer flow.
- Per-reason retry scheduling, duplicate delivery, and out-of-order delivery are
  not repeated because those shared mechanisms already have dedicated evidence.

### Semantic-token trade-off

Semantic tokens were selected because they are deterministic, privacy-safe,
readable, compatible with the existing request contract, and independent of an
external account or network.

They do not test credential parsing, brand routing, or real integration
behavior. Their names also reveal the intended simulated outcome. The design
limits this coupling by interpreting tokens once at the authorization boundary
and using normalized domain reasons everywhere else. Responses, events, logs,
screenshots, and reports must not retain the submitted token.

## Test-level strategy

| Test level | Planned evidence |
|---|---|
| Unit | Every token maps to the correct reason; every reason has English and Japanese guidance; lifecycle invariants keep declined financial values at zero |
| API | New decline returns `201`; retrieval and replay preserve the reason; the response excludes the token; unknown reason remains safe |
| Integration | Payment and completed idempotency records exist; no ledger entry exists; one webhook exists with the same reason |
| Idempotency: identical request | Repeating the same key and payload returns the original complete response and creates no extra effect |
| Idempotency: conflicting request | Changing token, amount, currency, or reference with the same key returns `409` and changes no stored record |
| Stored reason retrieval | The retrieved payment contains the original normalized reason; authorized payments have no reason |
| Webhook consumer | One representative declined event is delivered, verified, consumed, and projected with the same reason |
| Browser | One representative reason produces suitable English and Japanese guidance without exposing its code |
| Exploratory | Guidance remains useful at desktop and mobile widths; refresh and normal interaction do not automatically resubmit an unchanged decline |
| Privacy | API bodies, events, logs, screenshots, traces, and reports contain no submitted token or sensitive input |

Every reason receives unit, API, integration, retrieval, and event-creation
coverage. Browser automation samples one reason in both languages. This avoids
duplicating six nearly identical browser journeys while still proving the
language boundary.

## Scenario summary

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| `DECL-01` | Available funds are insufficient | Store `insufficient_funds`, return a decline, and create no ledger effect | High | API and integration | Planned pytest |
| `DECL-02` | The amount exceeds an allowed limit | Store `limit_exceeded` and provide safe corrective guidance | High | API and integration | Planned pytest |
| `DECL-03` | The payment method has expired | Store `expired_payment_method` and guide the customer to update it | High | API and integration | Planned pytest |
| `DECL-04` | Verification information is incorrect | Store `verification_failed` without echoing submitted security information | High | API and integration | Planned pytest |
| `DECL-05` | The payment method is invalid or unavailable | Store `invalid_payment_method` and provide neutral replacement guidance | High | API and integration | Planned pytest |
| `DECL-06` | The decline reason is unfamiliar | Store `unknown`; API and UI remain stable and safe | High | Unit, API, and browser | Planned automated coverage |
| `FIN-01` | Any detailed decline completes | All financial amounts remain zero and the ledger stays empty | Critical | Domain and integration | Planned pytest |
| `RET-01` | A declined payment is retrieved later | Status and normalized reason match the original record | High | API and integration | Planned pytest |
| `IDM-01` | The same key and identical decline request are replayed | Return the original response with one stored effect set | Critical | API and integration | Planned pytest |
| `IDM-02` | The same key is used with a different token, amount, currency, or reference | Return `409`; original records remain unchanged and no new result is created | Critical | API and integration | Planned parameterized pytest |
| `WH-01` | A detailed decline commits | Create one sanitized version-one declined event with the same reason | High | Integration | Planned pytest |
| `WH-02` | A representative declined event is delivered | Consumer projection keeps the normalized reason and one applied version | High | Integration | Planned pytest |
| `LOC-01` | Each reason is checked in both languages | Every mapping exists, is nonempty, and does not equal the internal code | High | UI unit | Planned Node tests |
| `LOC-02` | Insufficient-funds guidance is shown in English and Japanese | Same backend reason; language-appropriate visible guidance; no code shown | High | Browser acceptance | Planned Cucumber-JS and Playwright |
| `UI-01` | A declined result remains on screen without customer action | Checkout does not automatically send an unchanged request | Medium | Browser and exploratory | Planned observation and request count |
| `PRIV-01` | Retained surfaces are inspected | No payment token, sensitive input, secret, or local filesystem path is exposed | High | Cross-layer | Planned assertions and review |

## Detailed critical scenarios

### IDM-02: same key with a conflicting decline request

#### Business risk

A client may reuse a key accidentally after changing payment information. If the
service silently returns the previous decline, the client may believe the new
information was processed. If it creates another result, idempotency protection
has failed.

#### Preconditions

- A fresh database is available.
- The first request uses a detailed decline token and a new idempotency key.
- The first declined payment, idempotency result, and webhook event have
  committed.

#### Steps

1. Submit the original request and record its complete response.
2. Reuse the same key after changing one fingerprinted field.
3. Repeat separately for token, amount, currency, and merchant reference.
4. Retrieve the original payment and related records after each conflict.

#### Expected result

- Every changed request returns HTTP `409` and `idempotency_conflict`.
- The original payment status, reason, values, and version do not change.
- No second payment, ledger entry, idempotency record, or webhook event exists.
- The response does not return the original payment as if it represented the
  changed request.

#### Planned evidence

- Parameterized API contract tests.
- Database integration assertions after every conflict.
- Existing general idempotency coverage remains green.

### FIN-01: decline reason does not become a financial effect

#### Business risk

Adding more decline branches could accidentally reuse approval behavior. A
declined attempt with an authorization ledger entry would corrupt balances even
if the visible status said `DECLINED`.

#### Preconditions

- A fresh database is available.
- Each approved semantic decline token is available as a test control.

#### Steps

1. Submit one new request for each decline token.
2. Retrieve the payment, ledger, idempotency record, and webhook event.
3. Compare the stored reason with the API and event reason.

#### Expected result

- Every payment is `DECLINED` with the intended normalized reason.
- Authorized, captured, and refunded values are zero.
- No ledger entry exists.
- One completed idempotency record and one declined webhook event exist.
- No submitted token appears in returned or retained evidence.

#### Planned evidence

- Parameterized domain, API, and persistence tests.
- Webhook payload assertions.
- Privacy assertions across serialized evidence.

## Browser acceptance examples

Only customer-visible behavior enters the runnable Cucumber suite. Technical
idempotency, persistence, and event cases remain business-readable in this
catalog and run through faster pytest layers.

```gherkin
Scenario Outline: Decline guidance follows the selected language
  Given the checkout is displayed in "<language>"
  And the payment outcome is insufficient funds
  When the customer submits the payment
  Then the payment is declined
  And the guidance is displayed in "<language>"
  And no internal decline code is displayed

  Examples:
    | language |
    | English  |
    | Japanese |
```

The browser step definitions may also check the payment ID and network request
count. Database and webhook assertions should remain in integration tests so
the scenario stays understandable to a business reviewer.

## Planned implementation sequence

1. Add the normalized domain reason, persistence invariant, API schema, token
   mapping, and backend tests.
2. Add reason-aware webhook payload and representative consumer evidence.
3. Present the exact English and Japanese message table for review before
   changing checkout copy.
4. Add UI mappings, Node coverage, and the approved browser scenario outline.
5. Execute a focused exploratory session for guidance, responsive behavior, and
   automatic resubmission.
6. Run the complete project gate and write a closing quality report with actual
   results, defects, limitations, and recommendation.

Each implementation slice should be reviewable on its own. A later slice must
not present an earlier planned scenario as passed without executed evidence.

## Entry criteria

- This catalog is reviewed and merged.
- Normalized reason names and semantic tokens remain provider-neutral.
- New response and retrieval fields are agreed before implementation.
- Database invariants distinguish declined and non-declined payments.
- Exact English and Japanese copy receives review before UI
  implementation.
- Existing idempotency, webhook, browser, and privacy baselines are green.

## Exit criteria

- All six outcomes have unit, API, integration, retrieval, and webhook-creation
  evidence.
- Identical retry and all four conflicting-request variations pass.
- Every decline has zero financial values and no ledger entry.
- One representative event passes through delivery and consumption.
- Every reason has English and Japanese message-map coverage.
- The representative browser reason passes in both languages.
- Exploratory evidence checks useful guidance and no automatic resubmission.
- Retained evidence contains no submitted token or sensitive value.
- The full Python and Chromium gates pass on supported CI versions.
- Genuine defects have numbered reports and regression coverage.
- The closing report clearly separates executed results from limitations.

## Review decisions

| Decision | Result | Reason |
|---|---|---|
| Keep one `DECLINED` state and store a separate reason | Approved | Lifecycle state answers what happened; reason answers why |
| Treat a valid decline as a processed payment result | Approved | The request is valid even when authorization is refused |
| Scope automatic resubmission prevention to the checkout | Approved | Backend idempotency cannot prevent separate requests that intentionally use new keys |
| Test identical and conflicting idempotency separately | Approved | They have different contracts and failure modes |
| Store and return a normalized reason instead of a raw external response | Approved | It supports investigation without adding sensitive or product-specific data |
| Avoid a new diagnostic HTTP endpoint | Approved | A secure support endpoint would require a separate authorization design |
| Test all message mappings but sample one reason in both browser languages | Approved | It proves localization without duplicating six slow journeys |
| Reuse existing webhook retry and replay evidence | Approved | Shared delivery behavior should not be repeated for every reason |
| Use semantic synthetic tokens | Approved | Deterministic privacy-safe controls fit the independent simulator boundary |

No catalog decision remains open. Exact customer wording intentionally remains
the next review checkpoint before the UI implementation slice.
