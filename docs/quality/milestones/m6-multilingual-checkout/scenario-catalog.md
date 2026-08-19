# Milestone 6 Multilingual Checkout Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Milestone | 6: English and Japanese checkout with Playwright |
| Status | Draft for review; scenarios are planned, not passed evidence |
| Owner | Sapta Y Husain |
| Planned delivery | Catalog PR, then checkout implementation PR |
| Test basis | `docs/payment-requirements.md`, `docs/test-plan.md`, and the Milestone 5 next risks |
| Previous evidence | [Milestone 5 quality report](../m5-webhooks-reconciliation/quality-report.md) |

## Executive summary

This milestone adds a small browser checkout in English and Japanese. It is a
customer-facing layer over the existing payment API. It will use synthetic
payment outcomes and will not collect card numbers, security codes, names,
addresses, or other real payment data.

The main risk is not visual appearance alone. A customer must enter an exact
amount, understand validation and payment results, and retry safely when the
outcome is uncertain. The same behavior must remain clear in both languages and
on a mobile-size screen.

This catalog defines the proposed behavior and evidence before implementation.
No scenario in this document should be described as passed until the checkout
tests have run and the closing quality report contains the results.

## Situation

Milestones 2 to 5 proved the payment behavior through domain, API, database,
webhook, and reconciliation tests. A real customer does not use those technical
interfaces directly. The project now needs a browser layer that shows whether
the same reliability rules remain understandable and usable.

KOMOJU lists automated testing, manual and exploratory testing, Playwright,
multilingual applications, mobile applications, backend systems, and debugging
as relevant skills. A focused multilingual checkout can demonstrate these areas
without turning the project into a large ecommerce application.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| JPY or USD input is converted incorrectly | Customer authorizes the wrong amount | Critical |
| A repeated click creates more than one payment | Duplicate financial effect and customer confusion | Critical |
| An uncertain timeout is shown as a definite failure | Customer retries unsafely or abandons a successful payment | Critical |
| Japanese content is missing or misleading | Japanese customer cannot understand the checkout result | High |
| Validation is visible but not announced or focused | Keyboard or assistive-technology user cannot recover | High |
| Mobile layout hides the action or result | Customer cannot complete checkout on a small screen | High |
| UI accepts data that the API rejects differently | Inconsistent behavior and difficult support investigation | High |
| Test controls look like real payment collection | Portfolio privacy boundary becomes unclear | High |
| Result disappears after refresh | Customer cannot confirm the payment outcome | Medium |
| Error text exposes a token, key, or internal detail | Security and privacy incident | High |

## Scope

### Included

- English and Japanese checkout content.
- A language switch that preserves entered values.
- Merchant reference, display amount, currency, and synthetic outcome inputs.
- Exact conversion from customer-facing JPY or USD text to integer minor units.
- Approved and declined authorization results.
- Validation, processing, success, decline, uncertain, and retry states.
- Reuse of the existing payment, idempotency, and retrieval APIs.
- Result recovery after page refresh.
- Keyboard operation and basic semantic accessibility checks.
- Desktop and 390 by 844 mobile viewport coverage.
- Playwright browser automation and a small manual language/layout review.

### Outside scope

- Real card numbers, CVV, bank accounts, wallets, or production payment methods.
- Customer name, email, address, shipping, tax, cart, login, or order management.
- Native iOS or Android applications.
- Professional translation certification.
- Full WCAG certification or every assistive technology.
- Visual perfection across every browser and device.
- Capture, refund, settlement, and reconciliation controls in the customer UI.
- Third-party scripts, analytics, cookies, or external network services.

## Proposed product contract

### Page and language

The checkout should be available at `/checkout?lang=en` and
`/checkout?lang=ja`. English is the documented fallback for an unsupported or
missing language value.

The visible heading, field labels, help text, validation, processing state,
payment result, retry guidance, and language-switch label should use the selected
language. The document `lang` attribute should also match.

The language switch should keep non-sensitive entered values. A customer should
not need to re-enter the reference or amount only because the language changed.

The proposed functional copy is below. It is intentionally short so errors and
results remain clear on mobile screens. Japanese wording will receive a manual
review during implementation, but the project will not claim professional
translation certification.

| Meaning | English | Japanese |
|---|---|---|
| Page title | Payment test | 決済テスト |
| Merchant reference | Order reference | 注文番号 |
| Amount | Amount | 金額 |
| Currency | Currency | 通貨 |
| Synthetic control | Test outcome | テスト結果 |
| Approval choice | Approve | 承認 |
| Decline choice | Decline | 拒否 |
| Submit action | Run test payment | テスト決済を実行 |
| Processing | Processing… | 処理中です… |
| Authorized result | Payment authorized | 決済が承認されました |
| Declined result | Payment declined | 決済が拒否されました |
| Uncertain result | The result is uncertain. Retry with the same details. | 結果を確認できません。同じ内容で再試行してください。 |
| Retry action | Retry | 再試行 |
| New checkout | New test payment | 新しいテスト決済 |
| Required validation | This field is required. | この項目は必須です。 |
| Amount validation | Enter a valid amount. | 有効な金額を入力してください。 |
| General error | We could not complete the request. Please try again. | 処理を完了できませんでした。もう一度お試しください。 |

### Inputs

The checkout should contain:

- merchant reference;
- amount shown in customer-facing currency units;
- currency choice of JPY or USD;
- a clearly labelled synthetic outcome choice;
- one primary submit button.

The synthetic choices represent approval and decline. They must be described as
test outcomes, not as real payment methods.

### Exact amount conversion

JPY accepts a positive whole number such as `2500`. A decimal JPY value is
invalid.

USD accepts a positive amount with zero, one, or two decimal digits. For
example, `25`, `25.5`, and `25.50` become 2,500, 2,550, and 2,550 minor units.
The conversion must use the original string and must not depend on binary
floating-point arithmetic.

The existing API limit of 999,999,999 minor units remains the upper boundary.

### Submission and result

The browser should send the existing `/payments` JSON contract and one
idempotency key. The key belongs to the active submission and remains the same
while the result is uncertain. A completed result clears the active key before
a new checkout begins.

The UI should prevent normal repeated clicks while a request is active. Backend
idempotency remains the financial protection if two requests still overlap.

A successful or declined result should show payment ID, merchant reference,
localized amount, currency, and status. The payment ID may be saved in browser
session storage so refresh can retrieve the same non-sensitive result from the
API.

### Uncertain result

When the API returns the existing `payment_timeout` response, the UI must not
say that payment failed. It should explain that the result is uncertain and
offer one retry action. The retry must reuse the same idempotency key.

Failure injection remains disabled in the normal application. Playwright may
enable the existing test mode and add the post-commit timeout header only for a
controlled reliability scenario.

### Accessibility and mobile behavior

Inputs need visible labels and useful error text. Validation should move focus
to an error summary or the first invalid field. Processing and result changes
should be announced through a live status region.

All actions should work with the keyboard. Meaning must not depend on color
alone. At the mobile viewport, the page should have no horizontal scrolling,
overlap, clipped result, or hidden primary action.

## Recommended implementation approach

Use a small FastAPI-served page with semantic HTML, focused CSS, and lightweight
JavaScript. Do not add React or another frontend framework for this milestone.

This recommendation keeps attention on payment behavior and QA evidence. It
also keeps the page fast, makes the accessibility structure easy to inspect, and
avoids a large build system that does not improve the planned scenarios.

Use Python Playwright so the browser suite shares the existing pytest fixtures,
database setup, reports, and CI language. Chromium should be the required pull
request browser. Firefox and WebKit may run in a manually triggered or scheduled
matrix if their runtime remains reasonable.

## Test data

Only synthetic values should be used. Representative examples are:

| Purpose | Value |
|---|---|
| English reference | `order-browser-001` |
| Japanese reference | `注文-東京-001` |
| JPY display amount | `2500` |
| USD display amount | `25.50` |
| Approved outcome | `tok_approved`, displayed only as a test approval choice |
| Declined outcome | `tok_declined`, displayed only as a test decline choice |

The raw synthetic token may exist in the request value, but it should not appear
in the result, URL, error text, screenshot name, or report.

## 1. Language and content

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| LOC-01 | Checkout opens with `lang=en` | English heading, labels, help, action, and document language are shown | High | E2E | Playwright |
| LOC-02 | Checkout opens with `lang=ja` | Japanese heading, labels, help, action, and document language are shown | High | E2E | Playwright |
| LOC-03 | Language is missing or unsupported | Page uses the documented English fallback without an internal error | Medium | E2E | Playwright |
| LOC-04 | Customer switches English to Japanese and back | Visible content changes and entered reference, amount, currency, and outcome remain | High | E2E | Playwright |
| LOC-05 | Validation, decline, uncertain, and success states are shown | Every customer-facing message uses the selected language | High | E2E | Parameterized Playwright |
| LOC-06 | Long Japanese help or error text is displayed | Text wraps without overlap, clipping, or horizontal page scrolling | Medium | E2E and manual | Playwright plus review |

## 2. Input and currency rules

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| INP-01 | JPY amount `2500` is submitted | API receives integer amount 2500 and result shows `¥2,500` or documented equivalent | Critical | Unit and E2E | Automated |
| INP-02 | USD amounts `25`, `25.5`, and `25.50` are submitted | API receives 2500, 2550, and 2550 minor units without floating-point error | Critical | Unit | Parameterized |
| INP-03 | JPY contains a decimal | Localized validation rejects it before a payment request | High | E2E | Playwright |
| INP-04 | USD contains more than two decimals | Localized validation rejects it before a payment request | High | E2E | Playwright |
| INP-05 | Amount is empty, zero, negative, spaced incorrectly, or non-numeric | Clear localized validation appears and no payment is created | High | Unit and E2E | Parameterized |
| INP-06 | Amount is at or above the API maximum | Exact boundary passes and the first value above it fails before submission | High | Unit | Automated |
| INP-07 | Merchant reference is empty, 64 characters, or 65 characters | Empty and 65-character values fail; 64-character value is accepted | Medium | Unit and E2E | Automated |
| INP-08 | Merchant reference contains Japanese text | Exact Unicode value reaches the API and result without corruption | High | E2E | Playwright |
| INP-09 | DOM is changed to send an unsupported currency or outcome | API rejects the request and UI shows a safe general error | High | E2E/API | Playwright and existing API |

## 3. Payment journeys

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| PAY-01 | English JPY approval is submitted | One authorized payment appears with correct reference and formatted amount | Critical | E2E | Playwright |
| PAY-02 | Japanese JPY approval is submitted | One authorized payment appears with Japanese content and exact reference | Critical | E2E | Playwright |
| PAY-03 | English USD approval is submitted | One authorized payment appears with exact two-decimal display | High | E2E | Playwright |
| PAY-04 | Japanese decline is submitted | Decline is clear, localized, and not presented as success | High | E2E | Playwright |
| PAY-05 | Completed result page is refreshed | Same payment is retrieved; no second authorization is sent | Critical | E2E | Playwright |
| PAY-06 | Language changes on a completed result | Same payment remains visible and content is reformatted in the selected language | Medium | E2E | Playwright |
| PAY-07 | UI result is compared with payment and webhook APIs | ID, amount, currency, reference, status, and single event agree | Critical | E2E/API | Playwright |

## 4. Idempotency and recovery

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| REL-01 | Customer clicks or presses submit repeatedly while processing | Primary action is disabled and one financial payment effect remains | Critical | E2E | Playwright |
| REL-02 | Two equivalent browser requests still overlap | Backend idempotency returns one original outcome and one payment event | Critical | E2E/integration | Automated |
| REL-03 | Request fails before reaching the API | Retry remains available, uses the active key, and later creates one payment | High | E2E | Playwright routing |
| REL-04 | Payment commits but the response becomes an injected timeout | UI shows an uncertain result, not a definite decline or failure | Critical | E2E | Playwright test mode |
| REL-05 | Customer retries the uncertain result | Same key returns the original payment with one ledger entry and one webhook event | Critical | E2E/API | Playwright |
| REL-06 | Non-retryable validation or conflict response is received | UI gives clear safe guidance and does not retry automatically | High | E2E | Playwright routing |
| REL-07 | Stored result ID is missing or no longer valid | Refresh shows a localized recoverable message and a new-checkout action | Medium | E2E | Playwright |

## 5. Accessibility and keyboard behavior

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| A11Y-01 | Page structure is inspected | One clear main heading, main region, form, and result/status region exist | High | E2E | Playwright DOM checks |
| A11Y-02 | Inputs are inspected | Every control has a visible associated label and helpful accessible name | High | E2E | Playwright |
| A11Y-03 | Checkout is completed using only Tab, arrows, Space, and Enter | Focus order is logical and every action remains available | High | E2E | Playwright keyboard |
| A11Y-04 | Invalid form is submitted | Focus moves to the error summary or first invalid control and errors are associated | High | E2E | Playwright |
| A11Y-05 | Processing or result state changes | Live region exposes the change without requiring visual observation | High | E2E | Playwright DOM checks |
| A11Y-06 | Success, decline, uncertain, and error styles are reviewed | Text and icons communicate meaning without color alone; visible focus remains clear | Medium | Manual | Review checklist |

## 6. Responsive and browser behavior

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| VIEW-01 | Checkout runs at 390 by 844 | No horizontal scroll, overlap, clipped message, or hidden submit action | High | E2E | Playwright viewport |
| VIEW-02 | Japanese validation and result run at mobile size | Long text wraps and retry/new-checkout actions remain usable | High | E2E | Playwright viewport |
| VIEW-03 | Checkout runs at a common desktop viewport | Form and result remain readable with stable layout | Medium | E2E | Playwright |
| VIEW-04 | Required browser suite runs from a clean CI checkout | Chromium installs and tests deterministically without an external service | High | CI | GitHub Actions |

## 7. Privacy and safe failure behavior

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| SAFE-01 | Form fields and network requests are inspected | No PAN, CVV, bank account, customer identity, or address field exists | Critical | E2E/manual | Playwright plus review |
| SAFE-02 | Result, URL, error text, screenshot names, and reports are inspected | Synthetic token, signing secret, and failure-control header are absent | High | E2E/manual | Automated assertion plus review |
| SAFE-03 | Synthetic outcome controls are displayed | They are clearly labelled as test outcomes and cannot be mistaken for real methods | High | E2E | Playwright |
| SAFE-04 | Failure header is attempted against a normal app | Existing safety rule returns 403 and UI cannot enable test mode itself | High | API/E2E | Automated |
| SAFE-05 | Unexpected 5xx or malformed response is returned | Localized general message appears without stack trace or internal configuration | High | E2E | Playwright routing |

## Detailed critical scenario

### REL-04 and REL-05: Japanese uncertain payment and safe retry

#### Business risk

A customer may submit a payment that commits successfully, but the browser may
receive a timeout before it sees the result. If the Japanese checkout says the
payment failed, the customer may try again with a new request and create an
unsafe duplicate.

The correct message and idempotency behavior must work together. Clear wording
without safe backend reuse is not enough, and backend safety without clear
customer guidance is also not enough.

#### Preconditions

- The checkout is open in Japanese with the controlled test application.
- Merchant reference is `注文-東京-001`.
- Amount is JPY `2500`.
- Synthetic approval is selected.
- The first payment request receives the existing post-commit timeout control.

#### Steps

1. Complete the form using the keyboard.
2. Submit once.
3. Let the API commit the authorization, ledger entry, idempotency response, and
   webhook event.
4. Return the injected timeout before the browser receives the payment result.
5. Observe the Japanese uncertain-result message and retry action.
6. Activate retry without changing the form.
7. Allow the second request to complete without failure injection.
8. Refresh the final result.
9. Compare the browser result with payment, ledger, and webhook evidence.

#### Expected result

- The first UI state says the outcome is uncertain; it does not say declined.
- The retry action is keyboard accessible and uses the same idempotency key.
- The second response returns the originally committed payment.
- Final content remains Japanese and shows JPY 2,500 as authorized.
- Refresh retrieves the same payment and sends no new authorization.
- Exactly one payment, authorization ledger entry, idempotency result, and
  webhook event exist.
- No synthetic token or failure-control value appears in the visible result or
  URL.

#### Planned evidence

- One Playwright journey through the real browser and HTTP boundary.
- API assertions for payment, ledger, and webhook event evidence.
- Screenshot and trace only on failure to keep normal CI artifacts small.
- A plain-English closing report that explains the customer and financial
  result.

## Planned test organization

The scenario count is not a target for separate test functions. Related examples
should use parameterization when one test technique proves the same rule.

Proposed files are:

- `tests/unit/test_checkout_money.py` for exact JPY and USD parsing;
- `tests/e2e/test_checkout_localization.py` for language and validation;
- `tests/e2e/test_checkout_payments.py` for approval, decline, and refresh;
- `tests/e2e/test_checkout_reliability.py` for repeated submit and timeout retry;
- `tests/e2e/test_checkout_accessibility.py` for semantics, keyboard, and mobile;
- one reusable Playwright server and isolated-database fixture.

The expected implementation is approximately 20 to 30 focused automated tests,
with parameterization covering the broader catalog.

## Entry criteria

- Proposed UI architecture is reviewed.
- English and Japanese content policy is agreed.
- JPY and USD display-to-minor-unit rules are agreed.
- Active idempotency key lifetime is agreed.
- Result recovery and uncertain-message behavior are agreed.
- Browser and mobile CI scope is agreed.
- No real payment or customer data field is required.

## Exit criteria

- Every critical scenario has automated evidence.
- English and Japanese approval, decline, validation, and uncertain states pass.
- JPY and USD conversion is exact at normal and boundary values.
- Repeated submit and uncertain retry create one financial effect.
- Refresh retrieves the same completed payment.
- Keyboard and mobile critical journeys pass.
- Normal application instances cannot enable failure injection.
- Browser artifacts and visible content contain no test token or secret.
- Existing unit, API, integration, webhook, and reconciliation suites still pass.
- CI passes on the documented Python and browser environments.
- Genuine defects and limitations are recorded in the closing quality report.

## Review questions

1. Approve lightweight FastAPI HTML/CSS/JavaScript instead of a frontend
   framework?
2. Approve customer-facing JPY whole units and USD decimal units with exact
   string conversion to API minor units?
3. Approve English fallback for a missing or unsupported language value?
4. Approve preserving entered non-sensitive values when language changes?
5. Approve storing only the active idempotency key and last payment ID in
   browser session storage?
6. Approve the Japanese post-commit timeout and safe retry as the centerpiece
   browser scenario?
7. Approve Chromium as the required pull-request browser, with Firefox and
   WebKit considered for a scheduled or manual matrix?
8. Approve 390 by 844 as the required mobile viewport while clearly stating
   that this is responsive-web evidence, not native-mobile testing?
9. Approve functional Japanese copy with manual review, without claiming
   professional translation certification?
