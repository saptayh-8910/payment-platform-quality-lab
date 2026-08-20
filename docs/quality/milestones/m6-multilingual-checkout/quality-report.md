# Milestone 6 Quality Report

## Document information

| Field | Value |
|---|---|
| Milestone | 6: English and Japanese checkout acceptance testing |
| Result | Proceed to Milestone 7 with documented limitations |
| Main implementation commit | `dbdd58f` |
| Closing test commit | `2462bc5` |
| Pull request | [PR #8](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/8) |
| Final feature CI run | [Run 32342298182](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32342298182) |
| Execution date | 2026-08-20 |

## Executive summary

Milestone 6 met its quality objectives for this privacy-safe simulator. The
project now has a small English and Japanese browser checkout over the existing
payment API. It accepts synthetic payment choices only and does not collect
card, bank, identity, address, or other real customer data.

The checkout keeps money conversion exact for JPY and USD. It explains approval,
decline, validation, and uncertain results in the selected language. It also
protects the customer and financial record when submission is repeated, a
successful response is lost after commit, or the browser refreshes the final
result.

The completed local quality gate contained 199 pytest tests with 98.40%
branch-aware coverage, 17 Node money tests, and 8 Cucumber scenarios with 58
steps. TypeScript checking, Ruff linting, Ruff formatting, and the Chromium
acceptance suite passed.

One genuine localization defect was found during manual mobile review. The
Japanese result displayed an English API status. The renderer now translates
customer-facing statuses, and automated regression evidence covers the fix.

The result supports progress to structured exploratory testing. It does not
prove native-mobile quality, professional Japanese translation, complete WCAG
conformance, or production payment readiness.

## Situation

Milestones 2 to 5 proved payment behavior through the domain, API, database,
webhook, and reconciliation layers. A customer does not interact with those
technical interfaces directly. A browser checkout was needed to show whether
the same safety rules remain clear and usable at the customer boundary.

This boundary adds different failure risks. The displayed amount can disagree
with the API amount. Japanese messages can be incomplete. A repeated action can
look harmless while it creates a duplicate payment. A timeout can be displayed
as a failure even though the payment already committed. Keyboard focus or a
mobile layout can also prevent a customer from understanding or completing the
journey.

The milestone therefore tested the visible message, browser behavior, HTTP
request, API result, and financial evidence as one connected system.

## Why these risks mattered

An incorrect amount or duplicate authorization is a direct financial risk. An
uncertain result shown as a definite failure may encourage an unsafe second
payment. A missing Japanese message or inaccessible validation can prevent a
customer from recovering without support.

Privacy was also part of the product contract. This project is a payment
simulator, so the checkout must not slowly grow into a form that collects real
payment or customer information. The allowed field list is now an exact API
test contract instead of a small blacklist of forbidden examples.

## Quality approach

The milestone used different test levels for different questions:

- Node unit tests checked JPY and USD string conversion and formatting without
  starting a browser.
- Pytest API tests checked the served HTML and asset contract, including the
  exact set of fields collected by the checkout.
- Cucumber-JS made the eight main business journeys readable as Given, When,
  and Then scenarios.
- TypeScript step definitions translated those scenarios into automation and
  kept scenario state in an isolated Cucumber World.
- A small page object kept browser selectors and repeated actions in one place.
- Playwright controlled Chromium, keyboard input, network behavior, isolated
  contexts, mobile viewport, refresh, screenshots, and traces.
- Existing pytest integration checks continued to prove payment, ledger,
  idempotency, webhook, and reconciliation behavior below the browser.
- A focused manual mobile review checked English and Japanese presentation and
  found a real localization defect.

This layering kept detailed combinations in fast tests while reserving the
browser suite for customer and full-stack risks.

## Important decisions

### One readable acceptance runner

Cucumber-JS owns the scenario lifecycle and reporting. Playwright is used as a
browser-control library inside Cucumber hooks and steps. The project does not
add Playwright Test or another adapter because a second runner would duplicate
lifecycle and reporting responsibilities.

### Exact string-based money conversion

The checkout converts the original amount string directly to integer minor
units. It does not use binary floating-point arithmetic. JPY accepts whole units,
while USD accepts zero, one, or two decimal digits.

### Browser and financial evidence together

Important reliability scenarios do not stop after checking a success message.
They compare the visible payment with API, ledger, idempotency, and webhook
evidence. This shows whether the customer result and financial effect agree.

### Same key after an uncertain result

When the first response is lost after commit, the checkout explains that the
result is uncertain. Retry reuses the original idempotency key. The final check
refreshes the page, retrieves the same payment, confirms only two payment
requests occurred, and confirms only one financial effect exists.

### Exact privacy allowlist

The checkout contract permits only merchant reference, amount, currency, and a
synthetic outcome. The API test collects every named input and select element
and compares the complete set with this allowlist. Adding any new collected
field now requires an explicit test and product review.

### One required pull-request browser

Chromium is the required browser for this milestone. This gives deterministic
pull-request feedback at a controlled runtime. Firefox and WebKit remain useful
future checks, but they are not evidence claimed by this report.

## Happy-path evidence

The acceptance suite proves these successful customer journeys:

- English JPY approval with the correct visible amount and authorized result.
- Japanese JPY approval with the exact Unicode merchant reference.
- USD approval with exact conversion from `25.50` to 2,500 minor units and an
  exact two-decimal display.
- Keyboard-only checkout at the 390 by 844 mobile viewport.
- Completed-result recovery after browser refresh without a new authorization.

## Unhappy-path and recovery evidence

The suite also proves these failure and recovery journeys:

- Japanese decline is clear and is not displayed as success.
- Invalid input produces localized guidance and useful focus recovery without
  sending a payment request.
- Repeated submission remains one financial effect even if browser requests
  overlap.
- A post-commit response loss produces an uncertain Japanese message instead
  of a false decline.
- Retrying the uncertain payment uses the same idempotency key and returns the
  originally committed payment.
- Refresh after recovery keeps the same payment and does not send a third
  payment request.
- Failure screenshots and traces are sanitized before publication.

## Execution evidence

| Evidence | Result |
|---|---|
| Full pytest suite | 199 passed |
| Branch-aware Python coverage | 98.40% |
| API route coverage | 100% |
| Node money tests | 17 passed |
| TypeScript type checking | Passed |
| Cucumber acceptance | 8 scenarios and 58 steps passed |
| Chromium browser gate | Passed |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Working tree whitespace check | Passed |
| Python 3.12 CI | Passed |
| Python 3.14 CI | Passed |
| Chromium acceptance CI | Passed |

The approved risks and scenario IDs are listed in the
[Milestone 6 scenario catalog](scenario-catalog.md). The browser suite produces
HTML, JSON, and JUnit reports. Failed scenarios attach a screenshot and
Playwright trace; passing scenarios do not create unnecessary failure files.

## Central reliability scenario

The Japanese uncertain-payment scenario is the strongest full-stack example in
this milestone:

1. Cucumber reads the business scenario.
2. The TypeScript step asks Playwright to submit the Japanese checkout.
3. Chromium sends a payment request with a controlled post-commit timeout.
4. FastAPI commits the payment, ledger entry, idempotency response, and webhook
   event, but the browser receives an uncertain result.
5. The customer retries using the same visible action and idempotency key.
6. FastAPI returns the original committed payment instead of creating another
   effect.
7. The browser refreshes and retrieves the same result.
8. API checks confirm one payment effect, one ledger entry, and one webhook
   event.

This scenario connects customer communication, browser behavior, HTTP failure
recovery, idempotency, persistence, and financial evidence in one understandable
journey.

## Defect and observation

### DEF-005: Japanese result showed an English status

Manual mobile review found that the Japanese approval heading and amount were
localized, but the status value remained the raw English API state
`AUTHORIZED`. This created a mixed-language result at the most important point
of the journey.

The browser renderer now maps API status values to the selected language. The
Japanese approval, decline, refresh, and uncertain-retry scenarios provide
regression evidence. See
[DEF-005](../../../defects/DEF-005-unlocalized-checkout-status.md).

No critical or high defect remains open for the declared Milestone 6 scope.

## Manual review evidence

A focused visual review was completed for the English and Japanese checkout at
the required mobile viewport. The review considered heading and label language,
long-text wrapping, action visibility, visible result state, and mixed-language
content. It found DEF-005 and confirmed the corrected Japanese status after the
fix.

This was a focused milestone review, not the formal exploratory-testing session.
Milestone 7 will use a documented charter, time box, observations, and follow-up
decisions.

## Limitations

- Chromium is the only browser required and reported by this milestone.
- The mobile evidence is responsive-web testing, not native iOS or Android
  application testing.
- Japanese copy is functional project copy and has not received professional
  translation certification.
- The checks support keyboard and basic semantic accessibility, but they do not
  claim full WCAG conformance or complete assistive-technology coverage.
- SQLite and one local FastAPI process do not represent every production lock,
  network, queue, or multi-region behavior.
- Controlled failure injection represents selected failure points, not every
  possible infrastructure incident.
- The checkout uses synthetic outcomes and does not process real payments.
- The project does not claim production readiness or PCI DSS compliance.

## Release recommendation

Proceed to Milestone 7 with the stated limitations. All declared critical
checkout scenarios have automated evidence. English and Japanese customer
journeys pass, money conversion remains exact, uncertain retry and refresh
preserve one financial effect, the privacy allowlist is enforced, and the
required Python and Chromium CI jobs pass.

## Next quality risks

- Scripted acceptance examples may miss unexpected combinations or confusing
  customer behavior.
- Exploratory testing should challenge language switching, refresh, repeated
  actions, malformed browser state, long content, and recovery transitions.
- Observations need clear severity, evidence, and follow-up decisions.
- The exploratory session must distinguish a genuine product defect from an
  accepted simulator limitation.
