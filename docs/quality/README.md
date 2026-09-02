# Quality Evidence

## Purpose

This area explains how quality decisions were made and how the results can be
checked. It is written for engineers, product managers, QA engineers, and
business stakeholders. A reader should not need to understand the test code to
follow the main risks and conclusions.

The documents do not claim that this simulator is a production payment system.
They describe evidence from synthetic data, isolated databases, and controlled
failure conditions.

## Documentation lifecycle

Quality evidence is recorded throughout each milestone:

1. Before implementation, a scenario catalog records the risks, assumptions,
   planned tests, and expected results.
2. During implementation, genuine defects and important decisions are recorded
   when they are observed.
3. At milestone close, a quality report records the actual environment, results,
   limitations, and release recommendation.
4. At project close, the [project quality summary](project-summary.md) connects
   the evidence from all milestones.

For an exploratory milestone, the charter replaces the scenario catalog as the
planning artifact. The completed session record and closing report become the
executed evidence.

This approach keeps planned coverage separate from executed evidence. A planned
scenario is not presented as a passed test.

## Document map

| Milestone | Quality focus | Scenario catalog | Closing report | Status |
|---|---|---|---|---|
| 4 | Idempotency, concurrency, and failure recovery | [Catalog](milestones/m4-idempotency-recovery/scenario-catalog.md) | [Report](milestones/m4-idempotency-recovery/quality-report.md) | Complete |
| 5 | Webhooks and reconciliation | [Catalog](milestones/m5-webhooks-reconciliation/scenario-catalog.md) | [Report](milestones/m5-webhooks-reconciliation/quality-report.md) | Complete |
| 6 | English/Japanese checkout | [Catalog](milestones/m6-multilingual-checkout/scenario-catalog.md) | [Report](milestones/m6-multilingual-checkout/quality-report.md) | Complete |
| 7 | Exploratory testing and defect evidence | [Charter](milestones/m7-exploratory-testing/exploratory-charter.md) and [session](milestones/m7-exploratory-testing/session-record.md) | [Report](milestones/m7-exploratory-testing/quality-report.md) | Complete |
| 8 | Performance baseline and project closeout | [Catalog](milestones/m8-performance-baseline/scenario-catalog.md) and [implementation guide](milestones/m8-performance-baseline/implementation-guide.md) | [Report](milestones/m8-performance-baseline/quality-report.md) and [sanitized summary](milestones/m8-performance-baseline/example-summary.json) | Complete |

The [traceability matrix](traceability-matrix.md) connects requirements, risks,
scenarios, and evidence across the project.

The [project quality summary](project-summary.md) gives the final decision,
milestone story, genuine findings, evidence boundaries, and recommended review
path.

## Post-MVP enhancements

| Enhancement | Quality focus | Scenario catalog | Closing report | Status |
|---|---|---|---|---|
| 1 | Detailed declined-payment outcomes | [Catalog](enhancements/e1-detailed-decline-outcomes/scenario-catalog.md) and [exploratory session](enhancements/e1-detailed-decline-outcomes/exploratory-session.md) | [Report](enhancements/e1-detailed-decline-outcomes/quality-report.md) | Complete |
| UX-01 | Provider-neutral checkout experience | [Catalog](enhancements/ux1-checkout-experience/scenario-catalog.md) and [exploratory session](enhancements/ux1-checkout-experience/exploratory-session.md) | [Report](enhancements/ux1-checkout-experience/quality-report.md) | In progress: local gates passed; pull-request CI pending |

An approved enhancement catalog records intended behavior, not passed evidence.
Closing reports record executed local and pull-request CI evidence.

Future milestones and enhancements use the same
[scenario catalog template](templates/scenario-catalog-template.md) and
[quality report template](templates/quality-report-template.md). The templates
keep the evidence consistent without forcing every milestone to use the same
test techniques.

## Evidence standard

A closing report must state:

- the commit and pull request that were tested;
- the test environment and runtime versions;
- the planned and executed test scope;
- the automated result and coverage result;
- genuine defects, observations, and known limitations;
- a clear recommendation to proceed, proceed with limitations, or stop.

JUnit and coverage XML files remain GitHub Actions artifacts. The repository
stores the human-readable explanation and links to repeatable automated tests.

## Writing standard

The documents use plain English at approximately IELTS 6.0 level:

- short sentences and active voice;
- one main idea per paragraph;
- business impact before implementation detail;
- technical terms explained when first used;
- exact evidence instead of broad claims;
- honest limits and non-goals.

For example, instead of saying "optimistic concurrency prevents stale aggregate
mutation," the report says: "A version number stops an older request from
overwriting a newer payment result."

## Status terms

- **Draft for review:** planned coverage that has not been approved or executed.
- **In progress:** implementation or testing has started.
- **Complete:** the closing report contains executed evidence.
- **Blocked:** a stated condition prevents a reliable result.
