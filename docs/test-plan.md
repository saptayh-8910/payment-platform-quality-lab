# Risk-Based Test Plan

## 1. Objective

Provide evidence that the simulated payment platform preserves financial
correctness, prevents duplicate effects, recovers predictably from failures, and
communicates defects clearly across service, database, webhook, and browser
boundaries.

## 2. Quality risks

| Priority | Risk | Potential impact | Primary evidence |
|---|---|---|---|
| Critical | Duplicate authorization, capture, or refund | Customer or merchant financial loss | Idempotency, concurrency, and ledger integration tests |
| Critical | Invalid lifecycle transition succeeds | Incorrect or unrecoverable payment state | Domain state-machine and API negative tests |
| Critical | Amount or currency precision error | Incorrect financial totals | Unit and property-based invariant tests |
| High | Ambiguous timeout causes an unsafe retry | Duplicate effect or unknown customer outcome | Post-commit timeout E2E scenario |
| High | Duplicate or out-of-order webhook changes state twice | Incorrect downstream records | Webhook consumer integration tests |
| High | API, ledger, and settlement disagree | Accounting and operational incident | Reconciliation tests and mismatch report |
| Medium | Japanese input or localized errors fail | Customer cannot complete checkout | Cucumber-JS and Playwright EN/JA tests plus exploratory sessions |
| Medium | Performance degrades under expected concurrency | Slow or failed payment attempts | k6 baseline and threshold report |
| Medium | Logs expose sensitive configuration | Security and privacy incident | Log assertions and manual review |

## 3. Test levels

### Unit

Test money validation, lifecycle transitions, request fingerprints, signature
verification, allocation logic, and reconciliation classification without I/O.
Use Hypothesis where generated operation sequences provide stronger invariant
coverage than enumerated examples.

### API

Validate request and response contracts, authentication placeholders, status
codes, validation failures, idempotency behavior, and error details through the
HTTP boundary.

### Integration

Exercise database transactions, unique constraints, ledger consistency,
concurrent writes, webhook persistence and consumption, failure injection, and
reconciliation against real SQLite storage.

### End to end

Cover a small number of critical journeys through the English/Japanese checkout
and API. Business-readable Gherkin scenarios run through Cucumber-JS, with
Playwright controlling the browser. The centerpiece is an authorization
committed before a simulated timeout, followed by a safe retry using the same
idempotency key.

### Manual and exploratory

Use risk-focused charters for behaviors that benefit from observation and
learning, including ambiguous recovery messaging, localized input, diagnostic
usefulness, and reconciliation investigation. Record session scope, evidence,
discoveries, defects, and follow-up automation decisions.

### Performance and reliability

Establish a small repeatable baseline for authorization and retrieval. Measure
throughput, p95 latency, error rate, and duplicate-effect count under concurrent
idempotent retries. Longer checks run outside the fast pull-request gate.

## 4. Initial coverage map

| Requirement area | Unit | API | Integration | E2E | Exploratory | Performance |
|---|---:|---:|---:|---:|---:|---:|
| Authorization and decline | Yes | Yes | Yes | Yes | Yes | Yes |
| Capture and cancellation | Yes | Yes | Yes | Limited | Yes | Later |
| Refunds | Yes | Yes | Yes | Limited | Yes | Later |
| Idempotency and concurrency | Yes | Yes | Yes | Yes | Yes | Yes |
| Webhooks | Yes | Yes | Yes | Limited | Yes | Later |
| Currency correctness | Yes | Yes | Yes | Yes | Yes | No |
| Reconciliation | Yes | API/CLI | Yes | Yes | Yes | No |
| English/Japanese checkout | Limited | No | No | Yes | Yes | Limited |

`Limited` means a representative critical journey, not exhaustive duplication
of lower-level coverage.

## 5. Environments and test data

- Unit tests use no external services or persistent database.
- API tests run the application in-process where possible.
- Integration and E2E tests use isolated temporary databases.
- Browser tests use synthetic English and Japanese customer data.
- Failure behavior is deterministic and selected explicitly per test.
- No suite depends on a paid API, production system, or real financial data.

Tests must be order-independent, parallel-safe where supported, and responsible
for their own setup and cleanup.

## 6. Automation and release gates

The planned fast pull-request gate includes:

- Ruff linting and formatting checks;
- unit, API, and integration tests;
- branch-aware coverage with an initial 85% threshold after the vertical slice;
- the small approved Cucumber-JS suite in Chromium when the UI exists;
- machine-readable test and coverage reports.

Scheduled or manually triggered workflows will contain longer browser,
concurrency, fault-recovery, and performance suites. External unreliability must
not be introduced into deterministic merge checks.

## 7. Manual release checklist

Before a portfolio release:

- All required automated gates pass from a clean checkout.
- Critical payment invariants pass with no unexplained exclusions.
- The timeout-and-safe-retry demonstration is reproducible.
- Concurrent equivalent requests produce one stored response and financial effect.
- Stale competing requests cannot overwrite a newer payment version.
- Reconciliation reports no unexplained mismatch.
- Open critical or high defects are documented and block release.
- Exploratory sessions cover changed high-risk behavior.
- Performance results meet the documented baseline or deviations are explained.
- Logs and generated reports are reviewed for secrets and sensitive test data.
- README commands and architecture statements match actual behavior.

## 8. Defect workflow

Defects discovered during implementation or exploration will be recorded with:

- summary, environment, and affected requirement;
- severity and customer or financial impact;
- minimal reproduction steps and evidence;
- expected and observed behavior;
- root cause and resolution when known;
- regression coverage or a documented reason not to automate.

Only genuinely observed defects will be presented as findings. Deliberate failure
injection scenarios will be labeled as test fixtures, not discovered bugs.

## 9. Entry and exit criteria

### Milestone entry

- Applicable requirements and open decisions are reviewed.
- Acceptance examples include success, boundary, and failure behavior.
- Required deterministic test controls are available or planned with the change.

### Milestone exit

- Automated tests pass at the appropriate levels.
- Relevant financial invariants remain true.
- Manual or exploratory evidence is captured when appropriate.
- New defects are resolved or explicitly accepted and documented.
- Documentation and traceability reflect the delivered behavior.
