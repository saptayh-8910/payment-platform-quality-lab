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
| Exploratory quality | Changed high-risk behavior must receive manual investigation | [Milestone 7 charter](milestones/m7-exploratory-testing/exploratory-charter.md) | Follow-up automation is selected from observed findings | Draft for review; execution not started |
| Performance | Expected load must meet a documented baseline | Milestone 8 plan | Planned | Planned |

## Maintenance rule

Scenario IDs are stable after approval. If a requirement changes, the catalog
records the change and this matrix is updated in the same pull request. A status
changes to complete only after the closing report contains executed evidence.
