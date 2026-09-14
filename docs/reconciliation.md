# Settlement and Reconciliation

## Purpose

Reconciliation checks whether independent financial records agree. A successful
API response is not enough evidence because a payment aggregate, ledger,
merchant webhook view, or external settlement file may still be incomplete or
incorrect.

This simulator imports synthetic settlement batches. It does not connect to a
bank, payment provider, or real merchant.

## Settlement batch

Each batch has one immutable cutoff and an ordered list of source rows. Every
row contains a synthetic payment ID, an integer minor-unit amount, and a
currency. Source line numbers are stored so duplicate rows remain visible and
investigation results are repeatable.

An imported row must refer to a known payment created on or before the cutoff.
This prevents a source row from being silently excluded from the report.

The batch may intentionally contain:

- no row for an expected payment;
- more than one row for the same payment;
- an incorrect amount;
- an incorrect currency.

These conditions allow the report to demonstrate realistic mismatch handling.

## Cutoff rule

Expected settlement is calculated only from immutable ledger entries with
`created_at <= cutoff`.

```text
expected settlement = captured amount - cumulative refunds
```

A zero or negative expected balance does not require a settlement row. This
means declined, cancelled, and fully refunded payments can match without one.

The current payment aggregate is compared with the complete ledger separately.
This prevents a refund after the settlement cutoff from creating a false ledger
integrity warning.

## Settlement classification

| Classification | Meaning |
|---|---|
| `matched` | Expected and observed amount and currency agree, or both are absent for a zero balance |
| `missing` | A positive expected balance has no settlement row |
| `duplicated` | More than one source row refers to the same payment |
| `amount_mismatched` | One row exists, but its amount or currency differs |

For a duplicate, every row remains in the payment detail. The first source line
is used once in the summary total, so duplicate rows are not silently added to
the observed balance. The duplicate count still makes the report fail.

## Independent source checks

Each payment result also shows two checks outside settlement classification.

### Ledger check

The report compares authorization, capture, and refund totals in the payment
aggregate with totals calculated from immutable ledger entries. A
`CONFIRMATION_CAPTURE` contributes once to both the authorized and captured
totals because the delayed flow records one atomic financial event rather than
inventing a separate authorization. A difference is reported as `mismatched`
with both values shown.

### Webhook consumer check

The report compares the latest producer event with the processed-event inbox and
merchant projection.

- `missing` means the projection or latest processed event is absent.
- `stale` means the projection is behind the latest payment version.
- `mismatched` means the version is current but the financial content differs.
- `matched` means the latest consumer view agrees.

A matching settlement does not hide a ledger or webhook problem.

## Currency safety

All amounts use integer minor units. JPY and USD totals are reported separately.
The report never creates a cross-currency grand total.

If a JPY payment has a USD settlement row, the summary shows the expected JPY
shortage and the observed USD amount independently. See
[DEF-004](defects/DEF-004-mixed-currency-reconciliation-total.md).

## Read-only and repeatable behavior

Generating a report does not create or update payment, ledger, webhook,
settlement, or projection records. Running the same batch again returns the same
ordered details, counts, and totals.

## HTTP endpoints

| Endpoint | Purpose |
|---|---|
| `POST /settlement-batches` | Import an immutable synthetic batch and source rows |
| `GET /settlement-batches/{id}` | Inspect the imported batch in source-line order |
| `POST /reconciliation-reports` | Compare financial sources and save confirmation evidence on first generation |

## Confirmation evidence through cutoff

`confirmation_section` is separate from the existing financial summary. It
records `cutoff`, `generated_at`, delayed-payment outcome counts, final
confirmation disposition counts, pending receipt count, and observed anomaly
amounts grouped by submitted currency and disposition. Unknown references do
not become invented payments. Replay and ID conflicts do not add dispositions.
Anomaly amounts never enter expected settlement totals.

The first request saves this section for the settlement batch. Later requests
return the same section, while the existing current source-health checks may
change. This is effective-through-cutoff evidence known at generation, not an
exact reconstruction of what was known at the cutoff. Lifecycle events provide
the effective state; current mutable payment status alone is not used.

Recovery of a pre-cutoff pending receipt can appear in a new batch's report,
but cannot rewrite the saved section. To refresh, create another batch using
the desired cutoff and source rows. Revision `0006_reports` creates empty
snapshot storage; it does not invent earlier reports for historical batches.
First generation and competing confirmation writers are coordinated on SQLite.
Saving the section is atomic; a failed write leaves no partial section.

The report contains payment references and financial evidence but never includes
the synthetic payment token or webhook signing secret.

A sanitized [example mismatch report](quality/milestones/m5-webhooks-reconciliation/example-mismatch-report.json)
shows the exact API structure used for investigation evidence.

## Focused evidence

```bash
python -m pytest \
  tests/unit/test_reconciliation_rules.py \
  tests/integration/test_reconciliation.py \
  tests/api/test_reconciliation.py
```

The complete suite should also run because reconciliation depends on the payment
lifecycle and webhook consumer behavior.
