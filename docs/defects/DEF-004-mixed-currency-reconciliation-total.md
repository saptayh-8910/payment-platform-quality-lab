# DEF-004: Reconciliation summary combines different currencies

## Summary

The first reconciliation report design had one expected total, one observed
total, and one discrepancy for the complete settlement batch. This would add
JPY and USD minor-unit amounts together when a batch contained both currencies.

The arithmetic used integers, but the financial meaning was still wrong. For
example, JPY 1,234 plus USD 10.99 cannot be presented as one total of 2,333.

## Discovery

- Milestone: M5 webhook delivery and reconciliation
- Found by: risk review while designing the JPY and USD integration scenario
- Environment: local design and Python integration test suite
- Severity: High
- Status: Resolved in the reconciliation implementation PR

## Impact

A mixed-currency report could show a zero discrepancy even when the individual
currency positions were not clear. An investigator might read the batch as
financially balanced without knowing which currency had a shortage or excess.

No payment or ledger record was changed. The defect affected report accuracy
and the quality of financial evidence.

## Reproduction

1. Capture one JPY payment for 1,234 minor units.
2. Capture one USD payment for 1,099 minor units.
3. Add matching settlement rows for both payments.
4. Generate one reconciliation summary.

Expected: separate JPY and USD totals, each with zero discrepancy.

Original design: one expected total and one observed total of 2,333.

## Root cause

The first summary model treated integer minor units as directly comparable.
Integer storage prevents floating-point rounding, but it does not make amounts
from different currencies financially compatible.

The design focused on amount precision and missed currency grouping at the
summary boundary.

## Resolution

The report now groups expected, observed, and discrepancy totals by currency.
An observed row with the wrong currency is counted under its own currency. This
shows both sides of the problem, such as a JPY shortage and an unexpected USD
amount.

No cross-currency grand total is produced.

## Regression evidence

- `test_jpy_and_usd_totals_are_reported_separately` confirms that matching JPY
  and USD payments receive two independent zero-discrepancy totals.
- `test_amount_or_currency_difference_is_identified` confirms that a
  wrong-currency row appears as a shortage in the expected currency and an
  observed amount in the supplied currency.
- The API report test confirms the per-currency structure is clear and stable.

## Learning

Using integer minor units solves precision problems inside one currency. It does
not permit totals across currencies. Financial reports need currency as part of
the grouping key, not only as a label on each detail row.
