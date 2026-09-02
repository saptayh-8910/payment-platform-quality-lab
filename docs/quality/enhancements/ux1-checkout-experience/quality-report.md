# UX-01 Checkout Experience Quality Report

## Document information

| Field | Value |
|---|---|
| Enhancement | UX-01: Provider-neutral checkout experience |
| Result | Proceed to pull-request CI gate |
| Catalog commit | `6f0fd53` |
| UI and state commit | `a325c07` |
| QA and CI commit | `fe3c5ca` |
| Pull request | Pending |
| CI run | Pending |
| Local execution date | 2026-09-02 |

## Executive summary

The checkout now presents a clear simulator workspace beside a larger customer
payment surface. A tester controls the synthetic order and result in the
simulator region. The customer region shows only the order summary, a neutral
test payment method, one amount-labelled action, and the final result.

The redesign did not change payment business rules or backend contracts. The
complete Python suite remained at 264 passing tests with 96.57 percent branch
coverage. The browser-side suite increased from 30 to 45 passing Node tests.
The Cucumber suite increased from 10 to 11 passing cases and from 81 to 99
passing steps.

Local evidence supports progress to pull-request CI. UX-01 is not complete until
the Linux browser job verifies its Japanese font, all required checks pass, and
the final report records the pull request and CI run.

## Business problem

The earlier browser page proved strong payment behavior but looked like one
internal test form. A customer would never choose whether their payment should
be approved or declined. Showing that selector next to the payment action made
the demonstration less realistic and could confuse a reviewer.

The redesign needed to improve the presentation without weakening the more
important quality controls: exact money, one financial effect, safe retry,
localized decline guidance, result recovery, and privacy-safe evidence.

## Implemented design

### Clear responsibilities

- The simulator region contains reference, amount, currency, and synthetic
  outcome settings.
- The customer checkout contains no input for credentials and no decline
  control.
- The order summary updates locally and does not create a payment.
- The synthetic outcome never reveals the planned result before submission.
- A persistent environment notice tells the user not to enter real payment
  information.

### Customer action and result

- A valid amount appears in the order summary and payment action.
- Invalid or missing amounts keep the general payment label and use the existing
  localized validation behavior.
- Processing disables the payment action immediately.
- A final or uncertain result replaces the payment-method action area while the
  attempted order summary remains visible.
- Simulator fields become read-only through a disabled fieldset until a new test
  begins.
- On mobile, simulator controls collapse after a result so the customer outcome
  remains prominent.

### Responsive visual system

- Desktop uses a narrow simulator column and a larger checkout column.
- Mobile uses one column with an expanded-by-default simulator disclosure above
  the checkout.
- Original neutral symbols and colors avoid payment-network or provider
  branding.
- Local system fonts include a named Japanese fallback and no external font
  request.
- CSS tokens define important colors, spacing, radius, focus, and status styles.
- Reduced-motion preference limits the processing animation.

## Client-side architecture decision

UX-01 kept lightweight browser JavaScript, but it did not assume that direct DOM
code is automatically safe. A small pure module now owns:

- named editing, restoring, processing, final, uncertain, and error states;
- permitted transitions between those states;
- exact derived order summaries; and
- amount-labelled payment actions.

Invalid transitions fail explicitly. The DOM controller uses the state model to
centralize visibility, disabled controls, progress, results, and live status.
Node tests cover the state and derived values without starting a browser.

A framework migration remains outside this change because it would introduce a
new runtime, build system, and full page rewrite. It can be reconsidered if the
project later gains several pages or independent client states.

## Verified compatibility constraints

- `#outcome` remains the synthetic selector after moving into the simulator
  region, so the existing typed page object keeps its verified locator.
- All four collected fields and their names remain unchanged.
- The `/payments` request, idempotency header, safe retry packet, and completed
  result ID remain unchanged.
- The catalog mapped every earlier Gherkin journey. All ten earlier cases still
  run, and one new trust-boundary scenario was added.
- The approved Enhancement 1 decline messages remain unchanged.

## Automated evidence

| Evidence | Local result |
|---|---|
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Python suite | 264 passed |
| Branch-aware coverage | 96.57%; required minimum 85% |
| Node unit suite | 45 passed |
| TypeScript check | Passed |
| Cucumber-JS and Chromium | 11 scenarios and 99 steps passed |
| Focused checkout API contract | 4 passed |
| Git diff whitespace check | Passed |

The new Node evidence includes seven state and derived-view checks and eight
design-token contrast checks. The Cucumber evidence adds a critical
trust-boundary journey and strengthens exact order-summary and payment-action
assertions in existing scenarios.

## Japanese font control

The earlier CI job installed Chromium with its runtime dependencies but did not
prove that a Japanese glyph font was present. The browser job now installs
`fonts-noto-cjk`, refreshes the font cache, and fails unless
`Noto Sans CJK JP` is found before Cucumber starts.

This control prevents a Japanese layout check from silently measuring missing
glyph boxes. It does not replace human review of wrapping and readability.
The first pull-request run must confirm that the installation works on the
current Linux runner.

## Exploratory evidence

The [session record](exploratory-session.md) covers:

- English desktop configuration and approval;
- exact live reference and JPY amount agreement;
- result focus and retained order context;
- Japanese mobile configuration and detailed decline;
- expanded and collapsed simulator presentation;
- 390 by 844 overflow and element clipping measurements;
- browser console review; and
- 640-CSS-pixel single-column reflow pressure.

No product defect was found.

## Accessibility evidence

The design targets WCAG 2.2 Level AA contrast values for the changed visual
system:

- 4.5 to 1 for normal text; and
- 3 to 1 for large text, control boundaries, meaningful icons, states, and
  focus indicators.

Tests calculate the actual ratios for the main text, muted text, action,
success, decline, uncertain, focus, and control-border tokens. Browser checks
also cover semantic regions, visible labels, error focus, live status, keyboard
completion, selected language, and horizontal overflow.

## Privacy and external dependency evidence

- The checkout still accepts exactly reference, amount, currency, and synthetic
  outcome.
- No card, security-code, bank, address, email, or identity field was added.
- The customer checkout region contains no input or select control.
- The raw submitted token remains absent from result, storage, and retained
  browser evidence.
- The new browser scenario fails if the page requests an external font, image,
  analytics script, or runtime resource.
- No frontend framework or remote design asset was added.

## Defects and observations

No product defect was found during implementation or exploratory review.

A focused four-test pytest command initially triggered the repository-wide 85
percent coverage gate because it did not run the remaining tests. Repeating the
focused command with coverage disabled passed, and the complete suite later
passed at 96.57 percent. This was an execution-command issue, not a product or
test defect.

## Limitations

- Pull-request CI evidence is pending.
- Linux Japanese font verification is implemented but has not yet run in the
  pull-request environment.
- The interactive browser could not set native 200-percent page zoom. A
  640-CSS-pixel reflow proxy passed without overflow, but `VIEW-06` remains
  partial evidence.
- Browser automation covers Chromium. Firefox, WebKit, and native mobile remain
  outside the declared scope.
- Japanese structural copy received owner review but not professional
  translation certification.
- Automated contrast checks cover declared design-token pairs, not every pixel
  produced by font anti-aliasing or background blending.
- The work is not a complete screen-reader or WCAG conformance audit.

## Release recommendation

Proceed to the pull-request CI gate. The local evidence shows a clearer and more
credible checkout without a payment, idempotency, recovery, localization, or
privacy regression. Close UX-01 only after CI confirms the Japanese font and all
required tests on the clean Linux runner.

## Next quality risk

After UX-01 closes, Enhancement 2 can add asynchronous confirmation to the new
status surface. Its review must still define durable confirmation identity,
expiry, late arrival, concurrent confirmation, reconciliation, and customer
messaging before implementation begins.
