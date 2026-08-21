# Milestone 7 Exploratory Session Record

## Session information

| Field | Value |
|---|---|
| Session ID | `M7-S01` |
| Date and timezone | 2026-08-21, Japan Standard Time |
| Tester | Sapta Y Husain with controlled browser assistance |
| Start time | 14:16 JST |
| End time | 14:35 JST |
| Planned time box | 90 minutes |
| Actual time used | 19 minutes of focused execution, followed by defect resolution and regression work |
| Charter | [Milestone 7 exploratory charter](exploratory-charter.md) |
| Commit under test | `5cde81041e07a78ad898c016f3c42152912121b5` |
| Operating system | macOS 26.6, build 25G72 |
| Python | 3.14.7 |
| Node and npm | Node 24.12.0 and npm 11.6.2 |
| Browser tooling | Playwright 1.62.1 with Chrome for Testing 151.0.7922.34 |
| Viewports | 1280 by 720 desktop and 390 by 844 mobile |
| Application | Controlled FastAPI test server on loopback only |
| Database | Isolated temporary file-backed SQLite databases, reset between selected recovery paths |

The session closed before the maximum time because deterministic local controls
made resets and cross-layer checks fast. Every critical thread was touched, the
high finding was reproduced twice, and the remaining uncertain observations
were classified as gaps instead of being presented as defects.

## Mission

Explore how the payment simulator behaves outside the expected scripted
journeys, with special attention to state changes, interruptions, repeated
actions, multilingual recovery, privacy, and cross-layer financial evidence.

## Setup confirmation

- [x] The commit under test is recorded.
- [x] The baseline automated checks are green.
- [x] Only synthetic data was used.
- [x] The application used isolated temporary databases.
- [x] Failure injection was enabled only in the controlled test application.
- [x] Evidence locations were known and local.
- [x] No external payment or production service was contacted.

## Baseline evidence

| Evidence | Result before exploration |
|---|---|
| Pytest | 199 passed |
| Branch-aware coverage | 98.40% |
| Node money tests | 17 passed |
| TypeScript type checking | Passed |
| Cucumber acceptance | 8 scenarios and 58 steps passed |
| Ruff lint and formatting | Passed |
| Initial desktop checkout | English form rendered without horizontal overflow |
| Initial collected-field set | `merchantReference`, `amount`, `currency`, and `outcome` only |

## Starting data

| Purpose | Value |
|---|---|
| English reference | `explore-en-001` |
| Japanese reference | `探索-東京-001` |
| Mixed-script reference | `order-探索-001` |
| JPY amount | `2500` |
| USD amount | `25.50` |
| Initial language | English |
| Initial viewport | 1280 by 720 |

## Timeline notes

| Time | State or action | Observation or question | Evidence or next idea |
|---|---|---|---|
| 14:16 | Recorded commit, runtime, and isolated server details | The environment matched the approved local scope | Run the complete automated baseline |
| 14:17 | Ran Python, Node, TypeScript, Cucumber, and Chromium gates | All baseline checks passed | Start from the English desktop checkout |
| 14:19 | Reviewed the clean English checkout at 1280 by 720 | The page was readable, had no horizontal overflow, and exposed exactly four named fields | Move through completed and restored states |
| 14:20 | Authorized `explore-en-001`, changed to Japanese, and refreshed | ID, reference, amount, status, and language remained consistent | Compare browser and backend records |
| 14:21 | Paused the server after submit and pressed Enter again | Processing feedback remained visible and only one request and financial effect completed | Interrupt the connection at a different boundary |
| 14:22 | Stopped the server before submit, changed language during uncertainty, restarted, and retried | The message stayed honest and localized; the same retry created one payment effect | Try missing and stale result state |
| 14:23 | Replaced the database while the browser kept a completed payment ID | The checkout showed localized missing-result guidance and allowed a clean reset | Explore a committed payment whose response is lost |
| 14:24 | Lost the response after commit, then refreshed before retry | The uncertain result disappeared even though the payment existed | Record `OBS-01` and try a different new submission |
| 14:25 | Submitted different details after the refresh | The hidden old key caused a conflict and a general error; no second effect occurred | Reproduce from a clean English database |
| 14:26 | Repeated the post-commit loss and refresh in English | The same recovery loss occurred independently | Classify as High and select browser regression coverage |
| 14:27 | Tried a 64-code-point emoji reference and the next boundary | The 64-code-point value was accepted; automation could not prove native entry beyond `maxlength` | Record `OBS-02` as a product question and gap |
| 14:28 | Used Japanese validation at 390 by 844, then changed to English | Focus moved to the summary, text localized, and no horizontal overflow appeared | Correct the amount and complete the mobile journey |
| 14:29 | Completed the corrected mobile payment and switched back to Japanese | Result focus, Japanese copy, amount, reference, and 390-pixel layout remained correct | Review keyboard link activation separately |
| 14:30 | Tried keyboard activation of the validation-summary link | The test tool did not give reliable keyboard evidence for this link | Record `OBS-04` as a coverage gap, not a defect |
| 14:31 | Delivered webhook events and generated a reconciliation report | Payment, ledger, projection, and reconciliation evidence agreed | Review generated artifacts |
| 14:32 | Scanned pytest, coverage, Cucumber, screenshot, and trace locations | No secret or full failure header appeared; coverage XML contained an unnecessary local source path | Record `OBS-03` as an evidence improvement |
| 14:35 | Reproduced the main defect twice and completed the debrief | One High defect required a fix before milestone close | Keep the financial release gate closed until regression passes |

## Exploration coverage

| Thread | Status | Main combinations or states explored | Notes or finding IDs |
|---|---|---|---|
| EXP-01 State and recovery | Covered | Clean, validation, processing, uncertain, completed, restored, missing result, and new checkout | `OBS-01` |
| EXP-02 Repetition and impatience | Covered | Enter during processing, offline retry, refresh before retry, and a changed submission after uncertainty | `OBS-01` |
| EXP-03 Language and data integrity | Covered | English/Japanese changes during validation, uncertainty, completion, and refresh; Japanese and boundary Unicode references | `OBS-02` |
| EXP-04 Interrupted communication | Partial | Offline before request, delayed response, post-commit response loss, and stale backend data | Malformed JSON and a direct 5xx were not explored |
| EXP-05 Mobile, keyboard, and feedback | Partial | Mobile validation, focus, language change, corrected success, result focus, wrapping, and overflow | `OBS-04`; complete assistive-technology behavior was outside scope |
| EXP-06 Privacy and artifact safety | Partial | Exact fields, URLs, visible errors, generated reports, screenshot locations, trace policy, and storage design | `OBS-03`; no failed-scenario trace was retained |
| EXP-07 Cross-layer agreement | Covered | Visible result, payment API, ledger, idempotency count, webhook event, merchant projection, and reconciliation report | Sources agreed for normal and uncertain payments |

## Observation log

| ID | Type | Severity | Summary | Reproduced? | Evidence | Decision |
|---|---|---|---|---|---|---|
| `OBS-01` | Defect and automation candidate | High | Refresh removed the uncertain result and safe retry path after a committed payment response was lost | Yes, Japanese and English | Browser state plus payment, ledger, webhook, and idempotency records | Fix in Milestone 7 and add Cucumber regression coverage; see [DEF-006](../../../defects/DEF-006-uncertain-payment-lost-after-refresh.md) |
| `OBS-02` | Product question and coverage gap | Low | The meaning of the 64-character UI boundary for non-BMP input needs an explicit product decision | Partial | A 64-code-point emoji reference succeeded; entry beyond native `maxlength` was inconclusive | Keep the API and UI code-point rule; do not report a defect without reliable native-input evidence |
| `OBS-03` | Improvement | Low | Local coverage XML included an absolute workstation source path | Yes | Generated `coverage.xml` source element | Generate coverage with relative file paths |
| `OBS-04` | Coverage gap | Low | Keyboard activation of a validation-summary link was not observed reliably with the session tool | No reliable result | Focus movement to the summary passed, but link activation was inconclusive | Keep as a stated gap; use a dedicated accessibility check if this risk becomes a release condition |

## Detailed finding

### OBS-01: Refresh removed uncertain-payment recovery

**Type:** Defect and automation candidate.

**Severity:** High.

**Affected requirement or oracle:** Milestone 6 `REL-04` and `REL-05`, the
customer expectation of a safe retry, and the financial invariant that one
intended action creates one effect.

**Starting state:** The Japanese or English checkout contained valid synthetic
details. The controlled server committed the authorization but replaced the
first response with a timeout.

**Action or sequence:** Submit, observe the uncertain message, refresh before
using Retry, enter different details, and submit again.

**Expected behavior:** Refresh should keep enough recovery state to explain that
the result is uncertain and retry the original request with the same key.

**Observed behavior:** Refresh displayed a blank form and no recovery action.
The old idempotency key remained hidden in storage. Submitting different details
then produced a generic conflict message.

**Customer, financial, privacy, or operational impact:** A customer can lose the
only visible path to a payment that already exists. A later generic error does
not explain which payment was committed. This can cause confusion and a support
case. The server still prevented a duplicate financial effect.

**Cross-layer evidence:** Each reproduction produced one authorized payment,
one authorization ledger entry, one webhook event, and one idempotency claim.
The browser alone lost the connection to that result.

**Reproduction result:** Reproduced independently in Japanese and English with
fresh isolated databases.

**Sanitized evidence:** The committed reference, payment state, and source
counts are recorded here and in DEF-006. Temporary databases and browser images
were not retained.

**Decision and owner:** Resolve before closing Milestone 7. The checkout now
keeps a minimal active synthetic retry packet in tab-scoped `sessionStorage`,
restores the uncertain state after refresh, and clears incomplete or final data.

**Regression test decision:** Extend the existing critical Cucumber scenario so
refresh occurs before retry. The scenario must still prove the same key, same
payment, and one ledger and webhook effect.

## Financial evidence check

| Evidence | Expected | Observed | Agreement |
|---|---|---|---|
| Visible payment ID and state | Original authorized payment returns after safe retry | Original ID and authorized state returned after retry; before the fix refresh hid it | Agreed after recovery |
| Payment API | One JPY 2,500 authorized payment | One matching payment per intended journey | Yes |
| Ledger entries | One authorization entry | One authorization entry | Yes |
| Idempotency result | One claim and original response replay | One claim; retry returned the original response | Yes |
| Webhook event or consumer view | One version-1 authorization event and matching projection after delivery | One event and matching merchant projection | Yes |
| Reconciliation result | Authorized but uncaptured payment has zero settlement due and all sources match | Status `matched`, zero discrepancy, no ledger or projection mismatch | Yes |

## Privacy and artifact review

| Surface | Status | Observation or evidence |
|---|---|---|
| Form fields | Checked | Exactly four approved synthetic fields were present |
| URL and query values | Checked | Only the language and a field anchor appeared; no payment token, reference, or key appeared |
| Browser storage | Partial and design-reviewed | Before the fix, storage held the active key and last payment ID. The fix adds only the synthetic reference, integer amount, currency, and `approve` or `decline` retry choice while the result is uncertain; it does not retain the raw API token |
| Requests and responses | Checked | The request used the declared simulator contract; visible responses contained no secret or internal stack trace |
| Visible errors | Checked | Validation, uncertain, missing-result, and general messages contained no failure header, token, key, or stack trace |
| Screenshots | Checked | No screenshot was retained in the repository; temporary views used synthetic data only |
| Playwright traces | Partial | Passing scenarios produced no retained trace; sanitizer regression tests passed, but no failed-scenario trace was kept during this session |
| Cucumber HTML, JSON, and JUnit reports | Checked | No raw API token, signing secret, or full failure-control header appeared |
| Pytest and coverage reports | Checked | No secret appeared. `coverage.xml` contained an unnecessary absolute local source path, recorded as `OBS-03` |

## Automation decisions

| Observation | Automate? | Best test level | Reason | Follow-up |
|---|---|---|---|---|
| `OBS-01` | Yes | Cucumber-JS with Playwright and API evidence | The customer sequence crosses browser refresh, HTTP recovery, idempotency, and financial records | Refresh before retry is now part of the critical uncertain-payment scenario |
| `OBS-02` | No, not yet | Native browser or input-method boundary check | Expected behavior beyond `maxlength` is not agreed and the session evidence was inconclusive | Clarify the character-count rule before adding a test |
| `OBS-03` | Configuration check | Coverage generation | Relative paths improve portable evidence without changing product behavior | Enable coverage `relative_files` and rescan the generated XML |
| `OBS-04` | No, not yet | Focused accessibility automation or assistive-technology review | The current tool did not provide a reliable oracle for link activation | Keep the gap visible and revisit if the summary link becomes a release condition |

## Coverage gaps and blockers

- Not covered: Firefox, WebKit, native mobile, malformed JSON, direct 5xx
  routing, full Back/Forward history, and assistive technology.
- Partial: Direct mutation of every possible malformed browser-storage value.
- Blocked: Reliable keyboard activation evidence for the error-summary link.
- Environment concern: None. All services were local and deterministic.
- Follow-up charter needed: Not before Milestone 8. Create a focused browser or
  accessibility charter only if the listed gaps become release conditions.

## Debrief

### What was learned?

The backend safety controls remained strong during unusual browser actions. The
main weakness was continuity: the browser kept the idempotency key but not the
context needed to explain or retry an uncertain payment after refresh.

### What was most surprising?

The blank form looked like a clean reset while a committed payment and an old
active key still existed. The next submission exposed the hidden conflict, but
the message did not help the customer connect it to the original payment.

### Which risks increased or decreased?

Duplicate-charge risk decreased because every challenged path still produced
one effect. Recovery and support-investigation risk increased until DEF-006 was
fixed. Cross-layer confidence increased because reconciliation confirmed the
same story after webhook delivery.

### Which finding needed the fastest decision?

`OBS-01` needed a fix and regression check before milestone close because it
blocked a safe customer recovery path after a committed payment.

### Did the session direction change? Why?

Yes. The session moved from broad combinations to two clean reproductions and
cross-layer diagnosis when refresh removed the uncertain state. This produced
stronger evidence than continuing to sample unrelated low-risk combinations.

### Should another session be chartered?

Not now. The remaining gaps are explicit and do not block the simulator's next
milestone. A separate accessibility or browser-compatibility charter can be
created if those areas enter the release scope.

## Closing classification

| Measure | Result |
|---|---|
| Defects observed | 1 |
| Product questions | 1 |
| Accepted limitations | 0 |
| Improvements | 1 |
| Automation candidates | 1, implemented |
| Coverage gaps | 2 recorded observations plus stated scope gaps |
| Critical or high findings unresolved | 0 after follow-up fix and regression evidence |

## Session conclusion

- [x] No immediate stop condition remained after follow-up work.
- [x] Continue with the stated coverage limits.
- [ ] Pause the milestone decision.

## Evidence index

| Evidence ID | Description | Location | Retention or cleanup decision |
|---|---|---|---|
| `M7-E01` | Timestamped setup, combinations, observations, and debrief | This session record | Retain |
| `M7-E02` | Reproducible high defect with expected, observed, impact, cause, and resolution | [DEF-006](../../../defects/DEF-006-uncertain-payment-lost-after-refresh.md) | Retain |
| `M7-E03` | Business-readable regression sequence | `features/checkout/checkout.feature` | Retain and run in CI |
| `M7-E04` | Machine-generated pytest, coverage, Cucumber, screenshot, and trace evidence | `reports/` locally and GitHub Actions artifacts | Do not commit; retain in CI for 14 days |
| `M7-E05` | Closing decision and remaining limitations | [Milestone 7 quality report](quality-report.md) | Retain |
