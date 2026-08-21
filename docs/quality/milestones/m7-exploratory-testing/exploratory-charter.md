# Milestone 7 Exploratory Testing Charter

## Document information

| Field | Value |
|---|---|
| Milestone | 7: Structured exploratory testing and defect evidence |
| Status | Approved and executed; results are recorded in the closing quality report |
| Owner | Sapta Y Husain |
| Planned session length | 90 minutes |
| Test basis | Milestone 6 checkout report, risk-based test plan, and payment requirements |
| Session record | [Executed session M7-S01](session-record.md) |
| Closing evidence | [Milestone 7 quality report](quality-report.md) |
| Previous evidence | [Milestone 6 quality report](../m6-multilingual-checkout/quality-report.md) |

## Mission

Explore how the payment simulator behaves when a customer or investigator moves
outside the expected scripted journeys. Focus on confusing state changes,
interruptions, repeated actions, multilingual behavior, privacy, and disagreement
between the visible result and backend financial evidence.

The goal is to learn where the system surprises a reasonable user or makes an
incident difficult to investigate. The goal is not to repeat all eight Cucumber
scenarios or to produce a large number of findings.

## Situation

Milestone 6 proved eight selected checkout journeys with exact expected results.
Those tests are repeatable and useful for regression, but they follow known
paths. A real customer may refresh at an unusual time, switch language after an
error, retry impatiently, use damaged browser state, lose the network, or move
between actions in an order that was not predicted by a scenario.

An investigator also needs to connect the visible result with payment, ledger,
idempotency, webhook, and reconciliation evidence. A technically correct system
can still be difficult to support when its messages or records do not explain
what happened.

Exploratory testing is suitable here because actions and observations influence
the next question. The tester will use the charter as direction, not as a fixed
script.

## Why this matters

The most serious surprise would be one customer action producing more than one
financial effect. Other important risks include a definite message for an
uncertain outcome, loss of the original payment after refresh, mixed-language
content, unusable recovery controls, leaked synthetic controls, and backend
records that do not support the visible result.

These problems can affect customer trust, financial correctness, privacy, and
support investigation. They are difficult to understand from test counts alone.

## Questions the session should answer

- Can unusual action sequences create a second financial effect?
- Does the checkout remain honest when the browser cannot confirm the result?
- Do English and Japanese remain consistent through error and recovery states?
- Can a keyboard or mobile user recover after validation, timeout, or refresh?
- Does damaged or stale browser storage fail safely?
- Do the visible result and backend records tell the same story?
- Can an investigator understand what happened without exposing secrets or
  synthetic failure controls?
- Which discoveries deserve a stable automated regression check?

## Scope

### Included

- English and Japanese checkout behavior in Chromium.
- Desktop and 390 by 844 mobile viewports.
- Keyboard, pointer, refresh, back navigation, and language-switch actions.
- Clean, missing, stale, malformed, or unexpected `sessionStorage` values.
- Slow, interrupted, malformed, and unsuccessful HTTP responses created through
  controlled local test tools.
- Repeated submit, retry, refresh, and new-checkout actions.
- Approval, decline, validation, uncertain, restored, and general-error states.
- Visible payment comparison with payment, ledger, webhook, and reconciliation
  evidence.
- Browser storage, URL, network, screenshot, trace, and report privacy review.
- Questions about diagnostic usefulness and support investigation.

### Outside scope

- Real payment methods, card data, bank accounts, customer identity, or
  production traffic.
- Native iOS or Android applications.
- Professional Japanese translation certification.
- Complete WCAG certification or every assistive technology.
- Firefox, WebKit, and large device matrices during this time box.
- Sustained load or performance thresholds, which belong to Milestone 8.
- Penetration testing or a complete security assessment.
- Real payment provider, bank, DNS, queue, or multi-region failure behavior.

## Test environment

Record the exact values in the session record before exploration begins:

- Git commit under test.
- macOS and browser version.
- Python and Node versions.
- Chromium launched by the project Playwright installation.
- FastAPI test application with an isolated temporary SQLite database.
- Failure injection enabled only in the controlled test application.
- Desktop viewport and 390 by 844 mobile viewport.
- Network-routing or browser developer tools used during the session.

The session must not depend on an external service. Restarting the application
or clearing the temporary database is allowed, but each reset must be written in
the timeline.

## Synthetic test data

Use recognizable data so records can be connected across layers:

| Purpose | Example |
|---|---|
| English reference | `explore-en-001` |
| Japanese reference | `探索-東京-001` |
| Mixed-script reference | `order-探索-001` |
| JPY amount | `2500` |
| USD amount | `25.50` |
| Boundary reference | Exactly 64 synthetic characters |
| Approved outcome | Visible `Approve` or `承認` choice |
| Declined outcome | Visible `Decline` or `拒否` choice |

Create a new reference when a separate financial effect is intended. Reuse the
same reference and idempotency context only when testing retry or repetition.
Never enter real names, payment details, email addresses, or account data.

## User and investigation lenses

### Japanese mobile customer

The customer reads Japanese, uses a small screen, and needs clear validation and
recovery guidance. Look for mixed language, clipped content, hidden actions, lost
focus, and messages that assume technical knowledge.

### Impatient or uncertain customer

The customer does not know whether the first action worked. They click again,
press Enter, refresh, use Back, switch language, or choose a new payment while a
result is still uncertain. Look for duplicate effects and misleading certainty.

### Support investigator

The investigator begins with what the customer can see and tries to confirm the
same story in payment, ledger, webhook, and reconciliation evidence. Look for
missing identifiers, disagreement, unclear timestamps, and evidence that is
technically correct but difficult to use.

### Privacy reviewer

The reviewer checks what the page collects and what the browser, URL, network,
screenshots, traces, and reports retain. Look for any data outside the declared
synthetic field allowlist or any exposed secret and failure-control value.

## Exploration threads

The threads below are starting points, not scripted test cases. Follow useful
observations even when they cross from one thread into another. Mark what was
covered and what was not covered in the session record.

### EXP-01: State and recovery transitions - Critical

Move between clean form, validation, processing, uncertain, completed, restored,
missing-result, and new-checkout states. Refresh or change language at moments
that the automated scenarios do not select. Use Back and Forward when useful.

Observe which form values, result values, storage keys, and actions survive.
Watch whether the page presents old evidence as a new result or loses a result
that still exists in the API.

### EXP-02: Repetition and impatience - Critical

Combine mouse clicks, Enter, retry, refresh, and new-checkout actions around slow
or uncertain responses. Change the rhythm instead of only clicking twice at the
same speed.

Use payment, ledger, idempotency, and webhook evidence as the oracle. A disabled
button is useful, but one financial effect is the required result.

### EXP-03: Language and data integrity - High

Switch between English and Japanese before validation, during recovery, and
after a completed result. Use ASCII, Japanese, and mixed-script references. Try
normal and boundary-length synthetic values.

Look for mixed language, lost form values, changed payment identifiers,
incorrect amount formatting, stale error text, and URLs that disagree with the
visible language.

### EXP-04: Interrupted and damaged communication - High

Use controlled local routing to delay, abort, replace, or damage a response.
Consider an offline browser, HTTP error, invalid JSON body, missing payment, and
response loss after commit.

Observe whether the message is honest about certainty, whether retry remains
safe, and whether a new action can accidentally reuse or discard the wrong
idempotency key.

### EXP-05: Mobile, keyboard, and observable feedback - High

Explore with keyboard-only input at the mobile viewport. Follow focus through
language changes, validation, processing, uncertain result, retry, completed
result, and new checkout.

Look for hidden or clipped actions, horizontal movement, unclear focus, content
that depends only on color, and status changes that are not represented in the
live region or document structure.

This thread is a focused usability and semantic review. It does not claim a
complete accessibility audit.

### EXP-06: Privacy and artifact safety - High

Inspect form fields, browser storage, URL parameters, request and response data,
visible errors, screenshots, traces, JSON reports, and HTML reports. Trigger a
controlled failure when useful so failure evidence is available.

Check for data outside the four-field allowlist, signing secrets, raw failure
headers, synthetic outcome tokens, internal stack traces, and local paths that
do not help a reviewer. Sanitize evidence before it is committed or uploaded.

### EXP-07: Cross-layer agreement and diagnosis - Critical

Begin with a visible payment ID and reconstruct the result through the payment
API, ledger, webhook event, consumer view, and reconciliation report. Repeat
this after approval, decline, uncertain recovery, or an interrupted action.

Look for disagreement in ID, reference, amount, currency, state, event count, or
financial total. Also judge whether the evidence explains the customer result
in plain language.

## Oracles

An oracle is the source used to decide whether an observation is a problem. Use
more than one oracle when the behavior crosses layers.

| Oracle | What it helps judge |
|---|---|
| Payment requirements | Required lifecycle, idempotency, currency, and privacy behavior |
| Milestone 6 catalog | Approved checkout, localization, recovery, and accessibility rules |
| Customer expectation | Whether the message and next action are understandable and honest |
| Internal consistency | Whether similar states behave and communicate in similar ways |
| Financial invariant | Whether one intended action creates one reconcilable financial effect |
| Cross-layer comparison | Whether browser, API, ledger, webhook, and reconciliation evidence agree |
| Language consistency | Whether selected language, URL, labels, errors, result, and status agree |
| Accessibility semantics | Whether focus, labels, structure, and live feedback support recovery |
| Privacy boundary | Whether only declared synthetic data is collected and retained safely |

## Session time box

| Time | Activity |
|---:|---|
| 0-10 minutes | Record environment, create clean baseline data, and confirm the normal checkout works |
| 10-35 minutes | Explore state, recovery, repetition, and interrupted communication |
| 35-55 minutes | Explore language, mobile, keyboard, and observable feedback |
| 55-75 minutes | Compare browser results with backend evidence and review privacy artifacts |
| 75-85 minutes | Reproduce and classify important observations; capture minimal evidence |
| 85-90 minutes | Debrief, record coverage gaps, and decide follow-up actions |

The time allocation may change when a valuable finding appears. Record the
change and the reason. Do not extend the session silently; create another
charter or continuation session if important work remains.

## Note-taking and evidence rules

- Use the session record template and write timestamped notes during the work.
- Record ideas and questions, not only confirmed defects.
- Give every meaningful observation an ID such as `OBS-01`.
- Record the exact state, action, expected behavior, observed behavior, and
  oracle used.
- Capture the smallest useful screenshot, trace, response, or database evidence.
- Use synthetic references and remove secrets, failure controls, raw synthetic
  tokens, temporary paths, and unrelated local data before publication.
- Do not describe an injected failure as a discovered defect.
- Do not commit generated evidence unless it improves investigation and is safe
  to retain. CI artifacts may hold temporary machine-readable evidence.
- State when an observation could not be reproduced.

## Finding classification

Every observation must receive one of these outcomes:

| Type | Meaning |
|---|---|
| Defect | Observed behavior conflicts with an approved rule or reliable oracle |
| Product question | Expected behavior is unclear and needs a decision |
| Accepted limitation | Behavior is outside the declared simulator scope |
| Improvement | Current behavior works but could communicate or support investigation better |
| Automation candidate | A stable and valuable check should be added to regression coverage |
| Coverage gap | Important behavior was not explored or could not be observed reliably |

## Severity guide

| Severity | Meaning and examples |
|---|---|
| Critical | Duplicate financial effect, incorrect money, unrecoverable financial corruption, or exposed secret |
| High | Unsafe retry guidance, incorrect cross-layer result, blocked critical journey, or privacy-boundary failure |
| Medium | Confusing localized recovery, important keyboard or mobile problem, or weak diagnostic evidence with a workaround |
| Low | Minor wording, layout, consistency, or evidence-quality issue with little user impact |

Severity describes impact, not effort. A simple code change can still fix a
critical defect.

## Defect workflow

For each reproducible defect:

1. Preserve minimal sanitized evidence.
2. Confirm the affected requirement or oracle.
3. Check the payment, ledger, idempotency, and webhook effect when relevant.
4. Create the next genuine defect report under `docs/defects/`.
5. Record severity, environment, reproduction, expected result, observed result,
   impact, and current status.
6. Add a focused regression test when the behavior is stable and important.
7. If no automation is added, record why manual evidence is more suitable.

## Automation decision rule

Automate a discovery when it is repeatable, important, has a stable oracle, and
can run deterministically without hiding the business rule. Prefer the lowest
test level that proves it.

Keep the check manual when its value comes mainly from human judgement, visual
clarity, investigation usefulness, or changing combinations. Do not convert the
whole exploratory session into a large scripted suite.

## Entry criteria

- Milestone 6 code and closing report are merged.
- The branch under test has a clean automated baseline.
- The checkout and relevant evidence APIs run locally with synthetic data.
- Controlled failure tools are understood and disabled in the normal app.
- The session record is prepared with the exact environment and commit.
- The tester has reviewed this charter and the Milestone 6 limitations.

## Stop and pause conditions

Pause the session when:

- a critical financial or privacy finding needs evidence preserved immediately;
- real or sensitive data is entered accidentally;
- an uncontrolled external service or production system would be contacted;
- the environment becomes unreliable enough that observations cannot be trusted;
- a reset would destroy evidence needed for reproduction.

Record the reason, preserve safe evidence, and decide whether the session can
continue in another isolated environment.

## Exit criteria

- The 90-minute session and any approved time-box change are recorded.
- Each critical exploration thread is touched or explicitly marked not covered.
- All meaningful observations are classified and linked to evidence when useful.
- Every reproducible critical or high defect has a clear decision before
  milestone close.
- Financial effects are checked for findings involving submit, retry, refresh,
  or recovery.
- Automation candidates are implemented or given a documented reason to defer.
- The full automated suite still passes after any regression change.
- The Milestone 7 quality report records actual coverage, findings, limits, and
  the recommendation to proceed, proceed with limitations, or stop.
- The traceability matrix is updated only after executed evidence exists.

## Expected outputs

- One completed session record based on the approved template.
- Sanitized evidence for important observations.
- Genuine defect reports only for behavior actually observed.
- Focused regression tests for valuable stable discoveries.
- One Milestone 7 closing quality report.
- An updated traceability matrix and quality document map.

## Review decisions

1. Approve one 90-minute risk-focused session rather than a scripted checklist.
2. Approve Chromium desktop and mobile as the session browser scope.
3. Approve controlled local response manipulation for interruption exploration.
4. Approve the seven exploration threads and the stated priority order.
5. Approve the classification and severity rules.
6. Approve storing only sanitized, useful evidence.
7. Approve follow-up automation only when a discovery is stable and valuable.
8. Approve a second charter instead of silently extending the time box.
