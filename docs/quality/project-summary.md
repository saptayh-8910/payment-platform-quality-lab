# Payment Platform Quality Lab: Project Quality Summary

## Project decision

The initial eight-milestone project is complete with documented limitations.
The simulator demonstrates payment quality engineering across requirements,
code, APIs, databases, browsers, exploratory testing, performance, CI, and
plain-English release evidence.

It does not process real payments. It does not claim production capacity,
provider certification, PCI DSS compliance, or complete coverage of a real
payment platform.

## Business problem

Payment quality is more than checking whether a success page appears. A safe
system must prevent duplicate financial effects, preserve exact currency
values, recover from uncertain responses, deliver trustworthy events, and help
an investigator explain mismatches.

This project models those risks in a privacy-safe simulator. The tests check the
visible result and the stored financial evidence behind it.

## Delivered quality story

| Milestone | Main question | Evidence and result |
|---|---|---|
| 1: Foundation | What will be built, tested, and kept outside scope? | Requirements, lifecycle model, risk-based test plan, repository policy, and CI foundation |
| 2: Authorization | Can an approved or declined request persist safely? | Domain, API, and database tests; DEF-001 found and resolved |
| 3: Lifecycle | Do capture, cancellation, and refunds follow valid financial transitions? | Unit, property-based, API, and integration evidence for state and money invariants |
| 4: Reliability | Can retries and concurrent requests create duplicate effects? | [Scenario catalog](milestones/m4-idempotency-recovery/scenario-catalog.md) and [quality report](milestones/m4-idempotency-recovery/quality-report.md); claim-first idempotency, immutable responses, optimistic concurrency, and timeout recovery |
| 5: Platform consistency | Can webhooks and reconciliation explain the same payment? | [Scenario catalog](milestones/m5-webhooks-reconciliation/scenario-catalog.md) and [quality report](milestones/m5-webhooks-reconciliation/quality-report.md); signed delivery, duplicates, ordering, settlement, and cross-source reconciliation |
| 6: Customer journey | Can English and Japanese checkout journeys use the same safe backend behavior? | [Scenario catalog](milestones/m6-multilingual-checkout/scenario-catalog.md) and [quality report](milestones/m6-multilingual-checkout/quality-report.md); Cucumber-JS, TypeScript Playwright, Chromium, responsive and keyboard evidence |
| 7: Investigation | What happens when unusual customer and network actions are combined? | [Exploratory charter](milestones/m7-exploratory-testing/exploratory-charter.md), [session record](milestones/m7-exploratory-testing/session-record.md), and [quality report](milestones/m7-exploratory-testing/quality-report.md); DEF-006 found, fixed, and added to regression coverage |
| 8: Performance | Can a declared workload finish without losing financial correctness? | [Scenario catalog](milestones/m8-performance-baseline/scenario-catalog.md), [implementation guide](milestones/m8-performance-baseline/implementation-guide.md), and [quality report](milestones/m8-performance-baseline/quality-report.md); two complete passing baselines plus an investigated timing-gate failure |

The first post-MVP enhancement is complete. Detailed decline
outcomes preserve one `DECLINED` state and one normalized reason across the API,
database, idempotent replay, webhook projection, and English/Japanese checkout.
See its [scenario catalog](enhancements/e1-detailed-decline-outcomes/scenario-catalog.md),
[exploratory session](enhancements/e1-detailed-decline-outcomes/exploratory-session.md),
and [quality report](enhancements/e1-detailed-decline-outcomes/quality-report.md).

UX-01 is also complete. It separates simulator settings from the customer
checkout, adds an exact live order summary and amount-labelled action, and uses
one tested client-side state model for editing, processing, final, uncertain,
restored, and error presentation. Its
[catalog](enhancements/ux1-checkout-experience/scenario-catalog.md),
[exploratory session](enhancements/ux1-checkout-experience/exploratory-session.md),
and [quality report](enhancements/ux1-checkout-experience/quality-report.md)
record the design decisions, Japanese font control, regression mapping, local
evidence, pull-request CI, and limitations.

## Test architecture

Different test levels answer different questions:

- Unit and property-based tests challenge money rules and lifecycle invariants
  quickly.
- API tests verify contracts, validation, status codes, and safe retry behavior.
- Integration tests verify SQL transactions, concurrency, ledger entries,
  webhooks, and reconciliation using real SQLite storage.
- Cucumber scenarios express a small set of important customer journeys in
  business language.
- TypeScript Playwright controls Chromium and checks the visible English and
  Japanese checkout.
- Exploratory testing follows observations that were not known before the
  session began.
- k6 generates controlled traffic, while a separate Python verifier checks the
  financial records after load.
- GitHub Actions applies release gates and retains machine-readable evidence.

This separation avoids using a high test count as a substitute for meaningful
coverage. The [traceability matrix](traceability-matrix.md) connects each major
risk to its evidence.

## Automated evidence at project close

- 264 pytest tests with 96.57% branch-aware coverage.
- 45 Node money, decline-guidance, UI-state, derived-view, and contrast tests.
- 11 Cucumber scenarios with 99 passing steps.
- Chromium acceptance evidence for English, Japanese, responsive, keyboard,
  duplicate-submission, and uncertain-response recovery journeys.
- Python 3.12 and Python 3.14 CI coverage.
- Five performance profiles with exact traffic, timing, financial, and privacy
  gates.
- Two complete passing performance baselines on merged code.
- HTML, JSON, JUnit, coverage, screenshots, traces, and sanitized performance
  reports where appropriate.

## Genuine findings

The project records defects that were actually observed. Deliberate negative
tests are not presented as discovered bugs.

| Defect | Severity | How it was found | Resolution |
|---|---|---|---|
| [DEF-001](../defects/DEF-001-dependent-record-insert-order.md): authorization failed with foreign keys enabled | High | API and persistence integration testing | Resolved with correct transactional insert ordering |
| [DEF-002](../defects/DEF-002-idempotency-claim-rollback.md): failed operation retained an idempotency claim | Medium | Reliability integration regression | Resolved with explicit rollback behavior |
| [DEF-003](../defects/DEF-003-webhook-lease-datetime-comparison.md): webhook lease acquisition failed | High | Webhook delivery integration testing | Resolved with database-safe lease synchronization |
| [DEF-004](../defects/DEF-004-mixed-currency-reconciliation-total.md): reconciliation combined currencies | High | Risk review and integration design | Resolved with separate currency positions |
| [DEF-005](../defects/DEF-005-unlocalized-checkout-status.md): Japanese result exposed an English API status | Medium | Manual mobile review | Resolved with localized customer status text |
| [DEF-006](../defects/DEF-006-uncertain-payment-lost-after-refresh.md): refresh removed uncertain-payment recovery | High | Structured exploratory testing | Resolved and added to the critical Cucumber journey |
| [DEF-007](../defects/DEF-007-null-decline-reason-constraint.md): declined row accepted a null reason | High | Enhancement 1 database integration testing | Resolved with explicit null rejection and three invalid-combination regressions |

Milestone 8 also recorded a CI timing observation. One authorization run failed
its p99 guardrail while all financial checks passed. A focused confirmation and
the next complete run passed without changing code or thresholds. The event is
kept as evidence of runner variation and correct release-gate behavior.

## What the project proves

Within the declared simulator boundary, the evidence supports these statements:

- Equivalent retries produce one financial effect.
- Invalid transitions and over-refunds do not change stored financial state.
- JPY and USD remain in separate integer minor-unit positions.
- Payment, ledger, webhook, consumer, and settlement evidence can be reconciled.
- Duplicate and out-of-order events do not apply an older effect twice.
- English and Japanese customers receive selected safe checkout journeys.
- Six normalized decline reasons retain zero financial effect and map to useful
  English and Japanese guidance without exposing the submitted token.
- Simulator controls remain separate from a responsive customer checkout while
  exact amount, localization, idempotency, recovery, and privacy behavior stay
  covered.
- An uncertain response remains honest and can be retried with the original key.
- The declared performance workload completes without request loss or incorrect
  financial effects in two repeated passing baselines.
- CI blocks functional, coverage, browser, timing, financial, and evidence
  failures within the implemented gates.

## Known limitations

- The service uses one FastAPI process and SQLite. It is not a microservice or
  distributed-database capacity model.
- Chromium is the required browser; Firefox, WebKit, native mobile, and complete
  assistive-technology coverage remain outside scope.
- Japanese content has not received professional translation certification.
- Performance tests are modest regression checks, not stress, soak, disaster
  recovery, or production capacity tests.
- All data is synthetic. The project accepts no real cardholder or customer
  information.
- No real payment-provider API or sandbox is integrated.

## Recommended review path

A reviewer can understand the project efficiently in this order:

1. Read the root `README.md` for the system and commands.
2. Read the [risk-based test plan](../test-plan.md).
3. Review the [traceability matrix](traceability-matrix.md).
4. Read the Milestone 4 to 8 closing reports for executed decisions.
5. Open one defect report and its related automated test.
6. Review the Cucumber feature, Playwright step definitions, performance script,
   and financial verifier.
7. Inspect the latest GitHub Actions checks and retained artifacts.

## Post-MVP enhancement status

Enhancement 1 and UX-01 have passing local and pull-request CI evidence. Together
they add provider-neutral decline depth and a clearer customer checkout without
changing the declared simulator boundary.

Future enhancement work will keep the same review order: approve the scenario
catalog, implement a focused slice, execute automated and exploratory evidence,
and close it with a plain-English quality report. Product-specific values and
live data remain outside this independent repository.
