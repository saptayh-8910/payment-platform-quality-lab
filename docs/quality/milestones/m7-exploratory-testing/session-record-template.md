# Milestone 7 Exploratory Session Record Template

> This is a blank execution template. It is not evidence that exploration has
> occurred. Copy it to `session-record.md` only when the approved session begins.

## Session information

| Field | Value |
|---|---|
| Session ID | `M7-S01` |
| Date and timezone | |
| Tester | |
| Start time | |
| End time | |
| Planned time box | 90 minutes |
| Actual time used | |
| Charter | [Milestone 7 exploratory charter](exploratory-charter.md) |
| Commit under test | |
| Environment | |
| Browser and viewport | |
| Database or reset information | |

## Mission

Explore how the payment simulator behaves outside the expected scripted
journeys, with special attention to state changes, interruptions, repeated
actions, multilingual recovery, privacy, and cross-layer financial evidence.

## Setup confirmation

- [ ] The commit under test is recorded.
- [ ] The baseline automated checks are green.
- [ ] Only synthetic data will be used.
- [ ] The application uses an isolated temporary database.
- [ ] Failure injection is enabled only in the controlled test application.
- [ ] Evidence locations are known and writable.
- [ ] No external payment or production service will be contacted.

## Starting data

| Purpose | Value |
|---|---|
| English reference | |
| Japanese reference | |
| JPY amount | |
| USD amount | |
| Initial language | |
| Initial viewport | |

## Timeline notes

Write short notes while exploring. Include ideas, questions, changes of direction,
and resets. A note does not need to be a defect.

| Time | State or action | Observation or question | Evidence or next idea |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

## Exploration coverage

Use `Covered`, `Partial`, `Not covered`, or `Blocked`. A truthful gap is better
than a weak claim.

| Thread | Status | Main combinations or states explored | Notes or finding IDs |
|---|---|---|---|
| EXP-01 State and recovery | | | |
| EXP-02 Repetition and impatience | | | |
| EXP-03 Language and data integrity | | | |
| EXP-04 Interrupted communication | | | |
| EXP-05 Mobile, keyboard, and feedback | | | |
| EXP-06 Privacy and artifact safety | | | |
| EXP-07 Cross-layer agreement | | | |

## Observation log

Use one row for each meaningful observation. Classify it during the debrief if
the type is not clear when first observed.

| ID | Type | Severity | Summary | Reproduced? | Evidence | Decision |
|---|---|---|---|---|---|---|
| `OBS-01` | | | | | | |

Allowed types are Defect, Product question, Accepted limitation, Improvement,
Automation candidate, and Coverage gap.

## Detailed finding

Copy this section once for every observation that needs more than the summary
table.

### OBS-XX: Short title

**Type:**

**Severity:**

**Affected requirement or oracle:**

**Starting state:**

**Action or sequence:**

**Expected behavior:**

**Observed behavior:**

**Customer, financial, privacy, or operational impact:**

**Cross-layer evidence:**

**Reproduction result:**

**Sanitized evidence:**

**Decision and owner:**

**Regression test decision:**

## Financial evidence check

Complete this table for any observation involving submit, retry, refresh,
recovery, capture, cancellation, or refund. Use `Not applicable` when the
session did not touch a financial effect.

| Evidence | Expected | Observed | Agreement |
|---|---|---|---|
| Visible payment ID and state | | | |
| Payment API | | | |
| Ledger entries | | | |
| Idempotency result | | | |
| Webhook event or consumer view | | | |
| Reconciliation result | | | |

## Privacy and artifact review

| Surface | Checked? | Observation or evidence |
|---|---|---|
| Form fields | | |
| URL and query values | | |
| Browser storage | | |
| Requests and responses | | |
| Visible errors | | |
| Screenshots | | |
| Playwright traces | | |
| Cucumber HTML, JSON, and JUnit reports | | |

Confirm that retained evidence contains no real customer data, secret, signing
key, raw failure-control value, or unnecessary synthetic outcome token.

## Automation decisions

| Observation | Automate? | Best test level | Reason | Follow-up |
|---|---|---|---|---|
| | | | | |

Prefer the lowest stable level that proves the risk. Do not automate a finding
only to increase the test count.

## Coverage gaps and blockers

- Not covered:
- Blocked:
- Environment concern:
- Follow-up charter needed:

## Debrief

### What was learned?


### What was most surprising?


### Which risks increased or decreased?


### Which finding needs the fastest decision?


### Did the session direction change? Why?


### Should another session be chartered?


## Closing classification

| Measure | Result |
|---|---|
| Defects observed | |
| Product questions | |
| Accepted limitations | |
| Improvements | |
| Automation candidates | |
| Coverage gaps | |
| Critical or high findings unresolved | |

## Session conclusion

Choose one temporary session conclusion. The final milestone recommendation
belongs in the closing quality report after follow-up work and regression checks.

- [ ] No immediate stop condition observed.
- [ ] Continue with stated follow-up work.
- [ ] Pause release decision until listed critical or high findings are resolved.

## Evidence index

List only sanitized evidence that another reviewer can understand.

| Evidence ID | Description | Location | Retention or cleanup decision |
|---|---|---|---|
| | | | |
