# Quality Traceability Matrix

## Purpose

This matrix connects the payment requirement to its business risk, planned
scenario, and current evidence. It prevents a high test count from being used as
a substitute for relevant coverage.

## Current traceability

| Area | Requirement or risk | Scenario evidence | Automated evidence | Status |
|---|---|---|---|---|
| Idempotency | An equivalent retry must create one financial effect | M4 `IDM-01` to `IDM-03` | `tests/integration/test_payment_reliability.py` | Complete |
| Concurrency | A stale request must not overwrite newer payment state | M4 `CON-01`, `CON-02` | `tests/integration/test_payment_reliability.py` | Complete |
| Original response | A retry must return the original outcome | M4 `RPL-01`, `API-05` | Integration and API reliability tests | Complete |
| Pre-commit timeout | A failed transaction must leave no partial effect | M4 `FT-01`, `FT-02` | Integration and API reliability tests | Complete |
| Post-commit timeout | An uncertain client result must be safe to retry | M4 `FT-04`, `API-03`, `API-04` | Integration and API reliability tests | Complete |
| Failure control safety | Test controls must be disabled by default | M4 `API-01` | `tests/api/test_failure_recovery.py` | Complete |
| Ledger agreement | Payment totals must equal applicable ledger entries | M4 `LED-01` | `tests/integration/test_payment_reliability.py` | Complete |
| Webhook creation | A successful lifecycle change creates one event | M5 `W01` to `W08` | `tests/integration/test_webhook_delivery.py` | Complete |
| Signature verification | Invalid signed payloads must be rejected | M5 `S01` to `S05` | Unit and API webhook tests | Complete |
| At-least-once delivery | A duplicate delivery must not repeat an effect | M5 `D01` to `D08`, `C01` to `C09` | Integration and API webhook tests | Complete |
| Reconciliation | Payment, ledger, webhook, and settlement sources must agree | M5 `R01` to `R14` | Unit, integration, and API reconciliation tests | Complete |
| Multilingual checkout | English and Japanese journeys must remain usable | M6 `LOC-01` to `SAFE-05` and [closing report](milestones/m6-multilingual-checkout/quality-report.md) | Cucumber-JS, Playwright, Node unit, pytest API, and manual review evidence | Complete |
| Exploratory quality | Changed high-risk behavior must receive manual investigation | [Milestone 7 charter](milestones/m7-exploratory-testing/exploratory-charter.md), [session](milestones/m7-exploratory-testing/session-record.md), and [closing report](milestones/m7-exploratory-testing/quality-report.md) | DEF-006 refresh-before-retry regression in the critical Cucumber journey | Complete |
| Performance | Expected load must meet a documented baseline without losing financial correctness | [Milestone 8 catalog](milestones/m8-performance-baseline/scenario-catalog.md), [implementation guide](milestones/m8-performance-baseline/implementation-guide.md), and [closing report](milestones/m8-performance-baseline/quality-report.md) | Two complete passing k6 baselines, exact financial verification, an investigated timing-gate failure, PR smoke, weekly execution, and 14-day evidence retention | Complete |
| Detailed declines | Different declined outcomes must preserve one final state, one reason, no financial effect, safe retry behavior, and useful localized guidance | [Enhancement 1 catalog](enhancements/e1-detailed-decline-outcomes/scenario-catalog.md), [exploratory session](enhancements/e1-detailed-decline-outcomes/exploratory-session.md), and [quality report](enhancements/e1-detailed-decline-outcomes/quality-report.md) | 264 pytest tests at 96.57% coverage, 30 Node tests, 10 Cucumber scenarios with 81 steps, and six passing pull-request checks | Complete |
| Checkout experience | Simulator controls must remain separate from a clear responsive customer checkout without losing payment correctness, localization, recovery, accessibility, or privacy behavior | [UX-01 catalog](enhancements/ux1-checkout-experience/scenario-catalog.md), [exploratory session](enhancements/ux1-checkout-experience/exploratory-session.md), and [quality report](enhancements/ux1-checkout-experience/quality-report.md) | 264 pytest tests at 96.57% coverage, 45 Node tests, 11 Cucumber scenarios with 100 steps, verified Linux Japanese font, and six passing pull-request checks | Complete |
| Schema evolution | A known older database must upgrade without losing evidence; unknown or outdated schemas must not serve traffic as if ready | E2 `MIG-01` to `MIG-06`, `REG-M01`, [foundation report](enhancements/e2-asynchronous-payment-confirmation/migration-foundation-report.md), and [DEF-008](../defects/DEF-008-unversioned-local-database.md) | Four migration integration tests, 268-test Python regression, Chromium gate, and six passing pull-request checks | Complete |
| Asynchronous confirmation | A delayed payment must resolve from durable confirmation or explicit expiry without duplicate or ambiguous financial effects | [Enhancement 2 catalog](enhancements/e2-asynchronous-payment-confirmation/scenario-catalog.md) | Planned; no asynchronous-confirmation scenario is passed evidence yet | Approved plan |

## Maintenance rule

Scenario IDs are stable after approval. If a requirement changes, the catalog
records the change and this matrix is updated in the same pull request. A status
changes to complete only after the closing report contains executed evidence.
