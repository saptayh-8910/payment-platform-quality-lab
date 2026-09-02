# UX-01 Checkout Experience Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Enhancement | UX-01: Provider-neutral checkout experience |
| Status | Approved plan; implementation evidence is recorded separately |
| Owner | Sapta Y Husain |
| Owner review | Revised catalog approved on 2026-09-02 |
| Planned delivery | One focused pull request after design approval |
| Test basis | Existing multilingual checkout, completed detailed decline outcomes, accessibility rules, and payment reliability requirements |
| Required predecessor | Enhancement 1 merged and closed with owner-approved English and Japanese guidance; satisfied by PR #17 and its quality report |

## Executive summary

The current checkout proves the required payment behavior, but it presents the
simulator settings and the customer action as one simple form. A real customer
would not choose a decline reason or control the expected result. This weakens
the visual story even though the underlying tests are strong.

This enhancement proposes a clearer two-part experience:

1. a clearly marked simulator panel where a tester configures the order and
   synthetic outcome; and
2. a customer-facing checkout preview where the order, payment method, primary
   action, and result are presented in a familiar payment layout.

The change is visual and structural. It must not change payment lifecycle,
money conversion, idempotency, API, database, webhook, or reconciliation rules.
The planned scenarios in this catalog are not passed evidence. Results will be
recorded only after the design is approved, implemented, and tested.

## Situation

The project has grown from a small browser demonstration into a payment-quality
portfolio with multilingual journeys, failure recovery, and detailed decline
guidance. The page still looks like an internal test form. This is honest, but
it makes the customer journey harder to understand at first sight.

A stronger interface should make three facts immediately clear:

- this is a test environment and no real payment data is accepted;
- a tester controls the synthetic order and outcome outside the customer
  checkout; and
- the checkout itself behaves like a focused payment step with a clear amount,
  payment method, action, and result.

The next functional enhancement will add asynchronous confirmation. Improving
the layout first gives pending and delayed results a stable place in the
interface and avoids redesigning those states later.

## Verified baseline and dependencies

This draft was checked against the merged implementation rather than only the
earlier planning catalogs.

- Enhancement 1 is complete. Its
  [quality report](../e1-detailed-decline-outcomes/quality-report.md) records the
  merged pull request, owner-approved English and Japanese guidance, passing
  browser evidence, and release recommendation. Its scenario catalog remains a
  historical plan, so planned wording inside that catalog does not mean the
  implemented copy is still open.
- UX-01 starts from merged `main`, which contains the implemented guidance and
  its closing report. UX-01 must not alter that approved guidance unless a new
  owner copy review is recorded first.
- The current Gherkin feature contains nine scenario declarations. Its scenario
  outline has two language examples, so Cucumber executes ten cases. Every one
  is mapped explicitly later in this catalog.
- The current checkout page object selects the synthetic outcome with the
  literal locator `#outcome`. Moving that control into the simulator region
  must preserve this ID unless the owner approves a coordinated contract change.
- The current browser CI installs Chromium and its runtime dependencies, but it
  does not explicitly install or verify a Japanese glyph font. UX-01 must close
  this environment gap before using CI screenshots or layout measurements as
  Japanese rendering evidence.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| Simulator controls look like customer choices | A reviewer may mistake synthetic decline controls for a real checkout design | High |
| The amount is not visually important | A customer could act without clearly confirming what will be paid | High |
| The test boundary is unclear | A user may believe the page accepts real payment information | Critical |
| Visual work changes payment behavior | Existing idempotency, recovery, localization, or result retrieval may regress | Critical |
| Desktop design does not adapt to mobile | Controls, guidance, or the payment action may become difficult to use | High |
| Japanese content receives less space than English | Labels or guidance may wrap badly, overlap, or hide an action | High |
| Status meaning depends on color | Customers using assistive technology or with color-vision differences may misunderstand the result | High |
| A polished design copies another product's identity | The project may look misleading instead of original and provider-neutral | Medium |
| Extra UI code slows or destabilizes the checkout | Test reliability and customer interaction may become worse | Medium |

## Scope

### In scope

- A responsive checkout shell for desktop and mobile.
- A clear visual and semantic separation between simulator controls and the
  customer-facing checkout preview.
- A compact order summary showing reference, formatted amount, and currency.
- A neutral synthetic payment-method presentation that cannot be mistaken for
  a real card or wallet.
- A primary action that includes the localized formatted amount.
- Consistent approved, declined, uncertain, validation, processing, missing,
  and general-error states.
- English and Japanese copy for all new visible text.
- Keyboard, focus, live-region, contrast, zoom, wrapping, and responsive checks.
- Preservation of the existing API request, idempotency key, storage, refresh,
  retry, and localization behavior.
- Failure screenshots and traces through the existing browser test pipeline.
- One documented exploratory session after automated checks pass.

### Outside scope

- Real payment processing or collection of card, bank, wallet, address, email,
  or customer identity data.
- Copying another company's logo, colors, layout pixel-for-pixel, wording, or
  protected brand elements.
- A shopping cart, product catalog, tax, shipping, discount, login, or account
  journey.
- A client router, large component library, or unrelated frontend build-system
  expansion. The framework choice for the existing one-page checkout remains an
  explicit owner decision in this catalog.
- Changes to payment domain rules, API contracts, persistence, webhooks,
  reconciliation, or performance profiles.
- Implementing asynchronous confirmation behavior. UX-01 prepares a reusable
  status area; Enhancement 2 will define and test the pending lifecycle.
- Professional translation certification or a full accessibility conformance
  audit.
- Visual support claims for browsers not included in the declared test scope.

## Proposed design

### Desktop structure

```text
+---------------------------------------------------------------+
| Payment Quality Lab                         English | 日本語       |
| TEST ENVIRONMENT — do not enter real payment information       |
+-----------------------------+---------------------------------+
| Simulator controls          | Test checkout                   |
|                             |                                 |
| Order reference             | Order summary                   |
| Amount and currency         | Reference              ORDER-1 |
| Synthetic outcome           | Total                    ¥2,500 |
|                             |                                 |
| These settings control      | Payment method                  |
| the simulator only.         | Synthetic payment method       |
|                             | Test only                       |
|                             |                                 |
|                             | [ Pay ¥2,500 ]                  |
+-----------------------------+---------------------------------+
| Synthetic simulator only. No real payments are processed.     |
+---------------------------------------------------------------+
```

### Mobile structure

```text
+--------------------------------+
| Payment Quality Lab     EN | JA |
| TEST ENVIRONMENT               |
+--------------------------------+
| Simulator controls            |
| Order, amount, and outcome    |
+--------------------------------+
| Test checkout                  |
| Order summary                  |
| Total                   ¥2,500 |
|                                |
| Payment method                 |
| Synthetic payment method      |
|                                |
| [ Pay ¥2,500 ]                 |
+--------------------------------+
| No real payments are processed|
+--------------------------------+
```

On mobile, the compact simulator controls appear before the checkout because
the tester must configure the order before acting on it. The checkout remains
the larger and more prominent surface. The controls may use an
expanded-by-default disclosure section, but they must not become difficult to
discover or use with a keyboard.

### Proposed information hierarchy

1. Repository identity and language control.
2. Persistent test-environment notice.
3. Simulator configuration with an explicit explanation.
4. Customer-facing checkout title and order total.
5. Neutral synthetic payment method.
6. One clear primary payment action.
7. Result and recovery actions after submission.
8. Short privacy boundary in the footer.

### Proposed visual direction

- Use a calm neutral page background and a high-contrast checkout surface.
- Use one restrained accent color for actions, focus, and selected controls.
- Use spacing, type weight, border, and icons together; do not use color alone
  to communicate status.
- Keep the checkout width readable and avoid decorative content that competes
  with the payment action.
- Use a local system-font stack that names Japanese-capable fallbacks, including
  `Noto Sans CJK JP` for Linux CI. Do not load fonts from a remote service.
- Use a small set of CSS design tokens for color, spacing, radius, type, shadow,
  and focus treatment.
- Keep motion limited to the existing processing indicator and respect reduced
  motion preferences.
- Use simple original symbols where needed; do not display payment-network or
  provider logos.

### Declared accessibility targets

UX-01 targets the measurable parts of WCAG 2.2 Level AA that are directly
relevant to this redesign:

- normal text has at least `4.5:1` contrast against its background;
- large text has at least `3:1` contrast. For this catalog, large text means at
  least 24 CSS pixels when not bold or at least 18.66 CSS pixels when bold;
- visual information needed to identify a control, control state, meaningful
  icon, or focus indicator has at least `3:1` contrast against adjacent colors;
  and
- text can be resized to 200 percent without loss of content or functionality.

These targets follow
[WCAG 2.2 contrast and resize criteria](https://www.w3.org/TR/WCAG22/#distinguishable).
Passing these focused checks is not a claim of complete WCAG conformance.

## Proposed interaction rules

1. The simulator fields and the customer preview belong to one semantic form so
   keyboard submission and existing validation remain predictable.
2. Changing reference, amount, or currency updates the order summary locally
   without creating a payment.
3. Changing the synthetic outcome does not change the customer preview before
   submission. A customer should not be shown the planned result.
4. The primary action shows a formatted amount only when the amount is valid.
   With an invalid or empty amount, it uses the general localized payment label.
5. Pressing the primary action validates the simulator settings before sending
   the existing request.
6. While processing, the primary action is disabled immediately and its label
   communicates progress.
7. Validation stays close to its simulator field and is also summarized for
   keyboard and screen-reader users.
8. A final result replaces or follows the payment action without removing the
   order summary that explains what was attempted.
9. An uncertain result offers the existing safe retry. Retry uses the same
   idempotency key and the same immutable submission details.
10. A completed result can be refreshed or viewed in another supported language
    without sending another authorization request.
11. Starting a new test returns to an editable simulator state and clears the
    completed presentation as it does today.
12. The page never automatically submits a payment because a simulator control,
    language, viewport, or browser history state changed.

## Client-side architecture decision

The existing checkout already manages editing, validation, processing, final,
uncertain, restored, missing, and general-error behavior. The redesign adds a
derived order summary and amount-labelled action, but it does not add a new
payment lifecycle state.

| Option | Benefit | Cost and risk | Recommendation |
|---|---|---|---|
| Keep lightweight JavaScript and introduce an explicit UI state model | Avoids a framework migration, new build pipeline, and complete browser-test rewrite; reuses working payment behavior | State transitions and DOM updates remain the project's responsibility; ad hoc mutation could create REG-series defects | Recommended only with one named UI state, pure derived-view helpers, centralized rendering, and focused Node tests |
| Migrate this page to a frontend framework | Component boundaries and declarative rendering can make complex state easier to organize | Requires a new runtime and build setup, rewrites a currently passing page, changes test integration, and expands UX-01 beyond a visual redesign | Not recommended for UX-01; reconsider if later features create multiple pages or substantially more independent state |

The recommendation is therefore not that plain JavaScript is automatically
safer. It is that a controlled refactor of the current implementation has a
smaller change surface for this one-page enhancement. Owner approval is required
before this choice becomes an implementation constraint.

## Proposed customer-facing copy

The approved detailed decline guidance remains unchanged. The following table
covers only new or revised structural copy.

| Purpose | English | Japanese |
|---|---|---|
| Environment label | Test environment | テスト環境 |
| Environment warning | Do not enter real payment information. | 実際の決済情報は入力しないでください。 |
| Checkout title | Test checkout | テスト決済 |
| Order summary | Order summary | ご注文内容 |
| Total | Total | 合計 |
| Payment method | Payment method | 決済方法 |
| Synthetic method | Synthetic payment method | テスト用決済方法 |
| Method qualifier | Test only | テスト専用 |
| Simulator heading | Simulator controls | シミュレーター設定 |
| Simulator explanation | These settings control the test scenario. They are not customer payment choices. | これらの設定はテストシナリオを制御します。実際の決済方法ではありません。 |
| Valid amount action | Pay {amount} | {amount}を支払う |
| Amount not ready | Pay | 支払う |
| Footer boundary | Synthetic simulator only. No real payments or customer data are processed. | テスト用シミュレーターです。実際の決済情報や個人情報は処理しません。 |

Japanese copy in this draft is owner-review material and is not claimed as a
professionally certified translation.

## Proposed decisions and assumptions

| Decision | Status | Reason and trade-off |
|---|---|---|
| Separate simulator settings from customer checkout | Recommended | Makes the test harness honest while allowing the checkout to follow familiar payment patterns |
| Place simulator left and checkout right on desktop | Recommended | Both are visible without mixing their responsibilities |
| Place compact simulator controls before checkout on mobile | Recommended | The tester configures the order before acting; the checkout remains the larger visual surface |
| Keep semantic HTML and CSS; use lightweight JavaScript with an explicit UI state model | Needs owner approval | Avoids a framework migration, but accepts responsibility for centralized transitions, pure derived-view helpers, and direct regression tests |
| Keep one page instead of a multi-step journey | Recommended | The project tests payment behavior, not shipping, identity, or cart workflows |
| Use a neutral synthetic payment method | Recommended | Demonstrates a payment-method area without collecting or imitating real payment credentials |
| Put the amount in the primary action | Recommended | Gives the customer a final confirmation at the point of action |
| Preserve existing element IDs where their meaning is unchanged | Recommended | Reduces avoidable browser-test changes while allowing semantic improvements |
| Preserve `#outcome` when relocating the synthetic outcome control | Verified compatibility constraint | `CheckoutPage.enterPayment()` has a literal `page.locator("#outcome")` dependency |
| Add a reusable status surface but no pending behavior | Recommended | Prepares the layout for the next enhancement without claiming unimplemented lifecycle support |
| Avoid permanent screenshot baselines | Recommended | Exact pixel snapshots are brittle across font and browser updates; focused DOM checks and reviewed evidence better match this project |
| Keep Chromium as the pull-request browser | Existing decision | Maintains fast deterministic feedback; this enhancement does not expand browser-support claims |

## Scenario summary

### 1. Structure and trust boundary

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| UXS-01 | Checkout opens on desktop | Simulator controls and checkout preview are visually separate and both have clear headings | High | E2E and manual | Playwright plus review |
| UXS-02 | A reviewer inspects the customer checkout | No synthetic outcome choice appears inside the customer payment-method area | Critical | E2E | Playwright |
| UXS-03 | A reviewer inspects the full page | Test-environment notice is visible before any form interaction | Critical | E2E and manual | Playwright plus review |
| UXS-04 | The payment-method section is inspected | It says synthetic and test-only without a real brand, account number, or credential input | Critical | E2E | Playwright |
| UXS-05 | Page landmarks and headings are inspected | Header, main checkout, simulator region, status region, and footer form a logical structure | High | E2E | Playwright DOM checks |

### 2. Order summary and primary action

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| ORD-01 | Valid JPY amount `2500` is entered | Summary and action show the same localized `¥2,500` amount | Critical | Unit and E2E | Automated |
| ORD-02 | Valid USD amount `25.50` is entered | Summary and action show the same localized USD value with two minor digits | Critical | Unit and E2E | Automated |
| ORD-03 | Reference is changed before submission | Summary updates locally and no HTTP payment request is sent | High | E2E | Playwright request count |
| ORD-04 | Amount or currency is changed before submission | Summary and action update locally and no payment is created | Critical | E2E/API | Playwright plus API check |
| ORD-05 | Amount is empty or invalid | Action uses the general label; submission exposes localized validation and sends no request | High | E2E | Playwright |
| ORD-06 | Synthetic outcome is changed | Checkout preview does not reveal the planned success or decline | High | E2E | Playwright |

### 3. Existing payment behavior under the new layout

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| REG-01 | An approved JPY payment is submitted | Exactly one payment is authorized and the visible summary agrees with the API | Critical | E2E/API | Existing journey updated |
| REG-02 | A detailed decline is submitted | Localized approved guidance appears without exposing the raw token or internal reason code | Critical | E2E/API | Parameterized representative checks |
| REG-03 | Submit is activated repeatedly while processing | Action disables immediately and exactly one financial effect remains | Critical | E2E/API | Existing reliability journey |
| REG-04 | A committed response becomes uncertain | The layout shows uncertainty, not failure, and safe retry remains available | Critical | E2E | Existing timeout journey |
| REG-05 | An uncertain payment is retried | Same request and idempotency key recover the original result | Critical | E2E/API | Existing reliability journey |
| REG-06 | A completed result is refreshed | Same payment is retrieved and no new authorization occurs | Critical | E2E/API | Existing recovery journey |
| REG-07 | A completed or uncertain state changes language | Payment identity and financial values stay unchanged while visible copy updates | High | E2E | Playwright |
| REG-08 | New test payment is selected | Result clears and simulator controls return to an editable clean state | High | E2E | Playwright |
| REG-09 | A declined result remains open without customer action | No automatic resubmission occurs and the payment request count stays at one | High | E2E | Existing request-count journey |
| REG-10 | An uncertain result is refreshed before retry | The same immutable retry packet and localized uncertain state remain available | Critical | E2E | Existing recovery journey |
| REG-11 | Language changes before submission | Entered reference, amount, currency, outcome, and derived summary remain unchanged | High | E2E | Existing localization journey |

### 4. Responsive and localized presentation

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| VIEW-01 | English checkout opens at 1280 by 800 | Two-column layout is stable with no overlap or unnecessary horizontal scrolling | High | E2E and manual | Playwright plus review |
| VIEW-02 | Japanese checkout opens at 1280 by 800 | Labels wrap safely and checkout and simulator surfaces remain balanced | High | E2E and manual | Playwright plus review |
| VIEW-03 | Checkout opens at 390 by 844 | One-column layout keeps the summary, method, and payment action usable without horizontal scrolling | Critical | E2E and manual | Playwright plus review |
| VIEW-04 | Long Japanese decline guidance appears at 390 by 844 | Guidance, details, retry, and new-payment action remain visible and readable | High | E2E | Playwright |
| VIEW-05 | Viewport crosses the desktop breakpoint | Content reflows without duplicated controls, lost values, or an API request | High | E2E | Playwright |
| VIEW-06 | Page is zoomed to 200 percent at desktop width | Content reflows and all controls remain available without clipped text | High | Manual | Exploratory evidence |
| FONT-01 | Browser CI prepares Japanese rendering | CI installs `fonts-noto-cjk`, refreshes the font cache, and verifies `Noto Sans CJK JP` is available before Cucumber starts | Critical | CI | Workflow command plus retained log |

### 5. Accessibility and interaction quality

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| A11Y-01 | Keyboard user moves from page start through the form | Focus order follows the logical task and every interactive element has visible focus | Critical | E2E and manual | Playwright plus review |
| A11Y-02 | Simulator field is invalid | Error is visible, programmatically associated, included in the summary, and receives appropriate focus | High | E2E | Playwright |
| A11Y-03 | Processing or result state changes | Live region announces useful status without moving focus unexpectedly | High | E2E | Playwright DOM checks |
| A11Y-04 | Status surfaces are inspected without color | Text and a neutral symbol communicate approved, declined, uncertain, and error meaning | High | E2E and manual | DOM check plus review |
| A11Y-05 | Reduced-motion preference is active | Processing remains understandable without requiring animation | Medium | E2E/manual | Playwright emulation plus review |
| A11Y-06 | Text and interactive colors are measured | Normal text meets `4.5:1`; large text, control boundaries, meaningful icons, states, and focus indicators meet `3:1` against their applicable background | High | Automated/manual | Design-token check plus focused browser audit |
| A11Y-07 | English and Japanese language buttons are inspected | Current language is programmatically exposed and accessible names remain correct | High | E2E | Playwright |

### 6. Privacy, performance, and evidence safety

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| SAFE-01 | DOM, request, storage, logs, screenshots, and reports are reviewed | No real credential field, sensitive test token, secret, or customer identity appears | Critical | E2E and manual | Existing checks plus review |
| SAFE-02 | Page is opened from a clean browser session | No external font, analytics, image, or design dependency is requested | High | E2E | Playwright request inspection |
| SAFE-03 | UI assets are compared before and after | Redesign remains lightweight and does not add a frontend runtime or remote dependency | Medium | Review | File and network review |
| SAFE-04 | A browser scenario fails in CI | Existing screenshot, trace, HTML, JSON, and JUnit evidence remains available and sanitized | High | CI | Controlled verification |
| SAFE-05 | Checkout presentation resources load | Document, font, image, script, and stylesheet responses have no HTTP error | Medium | E2E | Playwright response inspection |

## Existing Gherkin scenario mapping

This table is a pre-implementation coverage contract. The current feature has
nine scenario declarations and ten executed cases because the detailed-decline
outline runs once in English and once in Japanese. No current journey may be
removed merely because the layout changes.

| Current `checkout.feature` scenario | Executed cases | UX-01 coverage IDs | Treatment in UX-01 |
|---|---:|---|---|
| English JPY payment is authorized | 1 | `ORD-01`, `REG-01` | Retain; update only layout-facing steps or assertions |
| Japanese JPY payment preserves its reference | 1 | `ORD-03`, `REG-11`, `VIEW-02` | Retain; also assert the derived summary remains stable |
| USD display amount is converted and shown exactly | 1 | `ORD-02` | Retain unchanged business assertion; add action-label agreement |
| Insufficient-funds guidance follows the selected language | 2 | `REG-02`, `VIEW-04`, `SAFE-01` | Retain both examples; use the Japanese case for focused mobile wrapping evidence |
| Declined result does not resubmit without customer action | 1 | `REG-09` | Retain request-count assertion |
| Invalid amount gives localized keyboard guidance | 1 | `ORD-05`, `A11Y-02` | Retain; update focus assertion only if the approved semantic structure requires it |
| Repeated submission creates one payment effect | 1 | `REG-03` | Retain as a critical financial regression gate |
| Japanese uncertain result is retried safely | 1 | `REG-04`, `REG-05`, `REG-10` | Retain commit-timeout, refresh, retry-packet, and one-effect assertions |
| Checkout completes by keyboard at the mobile viewport | 1 | `A11Y-01`, `VIEW-03` | Retain; adapt the tab sequence to the approved simulator disclosure |

Any future decision to supersede one of these journeys must name its replacement
scenario and show that the same business assertion remains covered. Renaming a
step or locator is not evidence that a scenario has been superseded.

## Detailed critical scenarios

### UXS-02: Simulator choices do not appear as customer payment choices

#### Business risk

If decline reasons appear inside the payment area, the page teaches an
unrealistic checkout pattern and may confuse a reviewer about what a customer
can control.

#### Preconditions

- The English checkout is open with the default synthetic settings.

#### Steps

1. Inspect the simulator region.
2. Inspect the customer checkout region.
3. Use keyboard navigation to reach the synthetic outcome control.
4. Change the outcome from approval to insufficient funds.
5. Observe the customer checkout before submission.

#### Expected result

- The outcome control belongs to the labelled simulator region.
- The customer payment-method area shows only a neutral synthetic method.
- The customer preview does not reveal the selected future result.
- Changing the outcome does not send a payment request.
- The test-environment notice remains visible.

#### Planned evidence

- Playwright landmark, ownership, visibility, and request-count assertions.
- Desktop and mobile exploratory screenshots stored only as review evidence.

### REG-03: Repeated activation creates one financial effect

#### Business risk

A visual redesign can accidentally move, duplicate, or re-enable the primary
action. Repeated activation could then create duplicate payment attempts.

#### Preconditions

- The checkout contains valid synthetic JPY settings.
- The controlled test application can delay the response.

#### Steps

1. Activate the payment action repeatedly with mouse and keyboard input.
2. Observe the action while the first request is active.
3. Wait for the final result.
4. Compare the browser result with payment, ledger, and webhook evidence.

#### Expected result

- The action becomes disabled immediately.
- Processing is visible and announced.
- The browser does not issue multiple normal submissions.
- One payment, one matching financial effect, and one event exist.
- The final summary agrees with the original order settings.

#### Planned evidence

- Cucumber-JS scenario using Playwright.
- Existing API and evidence endpoint assertions.
- Failure trace and screenshot if the scenario fails.

### VIEW-04: Long Japanese decline remains usable on mobile

#### Business risk

A desktop-focused design may pass automated payment checks while hiding the
guidance or recovery action needed by a mobile Japanese customer.

#### Preconditions

- Viewport is 390 by 844.
- Language is Japanese.
- The selected detailed decline uses long customer guidance.

#### Steps

1. Review the checkout and simulator layout before submission.
2. Submit the declined payment.
3. Read the complete guidance and result details.
4. Navigate to the new-payment action using the keyboard.
5. Measure document width against viewport width.

#### Expected result

- No horizontal page scrolling, overlap, or clipped text occurs.
- Status meaning is present in text and not color alone.
- Guidance and details remain readable.
- The recovery action remains visible and keyboard-operable.
- No internal reason code or synthetic token is visible.

#### Planned evidence

- Playwright mobile scenario.
- Owner-reviewed exploratory screenshot and notes.

## CI Japanese font prerequisite

The browser job must install and verify a known Japanese font before it runs
the Gherkin suite. Installing Chromium with its operating-system dependencies
does not by itself prove that Japanese glyphs are available.

The planned workflow step is:

```bash
sudo apt-get update
sudo apt-get install --yes fonts-noto-cjk
fc-cache --force
fc-match -f '%{family}\n' 'Noto Sans CJK JP' | grep 'Noto Sans CJK JP'
```

The command output becomes part of the CI log. Layout assertions still need
focused browser checks and human review because installed glyphs alone do not
prove good wrapping or readability.

## Implementation approach after approval

1. Confirm the merged Enhancement 1 quality report and owner-approved decline
   message module are present and unchanged.
2. Add the Japanese font installation and verification step to browser CI.
3. Run and record the current ten Cucumber cases before changing the page.
4. Define one explicit UI state model and pure derived-view helpers before
   changing DOM structure.
5. Restructure the existing semantic HTML without changing backend contracts or
   the verified `#outcome` locator.
6. Introduce a small CSS token layer and responsive two-surface layout.
7. Centralize browser rendering for live summary, amount-labelled action,
   processing, final, uncertain, missing, and error states.
8. Add focused Node tests for state transitions, derived formatting, and copy.
9. Update every mapped Gherkin journey without dropping its current business
   assertion.
10. Run Python, Node, TypeScript, Cucumber, lint, and Chromium gates.
11. Complete an English/Japanese desktop/mobile exploratory session, including
    Japanese glyph review and 200 percent zoom.
12. Record actual findings and limitations in a UX-01 quality report.

## Entry criteria

- Repository owner approves the desktop and mobile information hierarchy.
- Repository owner approves the new English and Japanese structural copy.
- Repository owner decides how simulator controls appear on mobile.
- Repository owner approves either the recommended lightweight-JavaScript state
  model or a separately scoped framework migration.
- Enhancement 1's merged quality report and approved decline message module are
  present. This dependency is currently satisfied and must remain satisfied.
- The `#outcome` ID is recorded as a verified page-object compatibility
  constraint before that control is moved.
- Browser CI is approved to install `fonts-noto-cjk` and fail when
  `Noto Sans CJK JP` cannot be verified.
- All ten currently generated Cucumber cases pass before implementation begins.
- The two local Enhancement 2 references remain outside this change.

## Exit criteria

- All approved UX-01 scenarios have recorded evidence or an explained manual
  limitation.
- Existing payment, idempotency, recovery, localization, API, database,
  webhook, reconciliation, and performance gates remain green.
- English and Japanese desktop and mobile exploratory checks are documented.
- Browser CI logs prove the declared Japanese font is installed before layout
  scenarios run.
- Every row in the existing Gherkin mapping is retained or has an explicitly
  approved replacement with the same business assertion.
- Recorded contrast results meet the numeric UX-01 targets for the reviewed
  design-token pairs and browser states.
- No real payment-data field or external design/runtime dependency is added.
- Any genuine defect found during the work is recorded and receives suitable
  regression coverage.
- The final quality report clearly separates automated evidence, manual
  observation, and untested claims.
- Pull-request CI passes from a clean checkout.

## Review questions

1. Do you approve separating simulator controls from the customer checkout?
2. On desktop, do you approve simulator controls on the left and checkout on
   the right?
3. On mobile, do you approve an expanded-by-default simulator disclosure above
   the checkout, which the tester can collapse after configuration?
4. Do you approve `Pay {amount}` and `{amount}を支払う` as the primary action?
5. Do you approve the remaining new English and Japanese copy in this catalog?
6. Should the result replace the payment-method area after submission, or appear
   below it while keeping the attempted method visible?
7. Do you agree that asynchronous pending behavior remains in Enhancement 2,
   while UX-01 only prepares the reusable result/status area?
8. Do you approve the recommended lightweight-JavaScript approach with an
   explicit UI state model, pure derived-view helpers, centralized rendering,
   and focused Node tests instead of a framework migration?
