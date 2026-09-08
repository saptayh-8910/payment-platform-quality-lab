"""Pure financial reconciliation rules."""

from datetime import UTC, datetime, timedelta

import pytest

from payment_quality_lab.persistence.models import (
    LedgerEntryRecord,
    SettlementRecord,
)
from payment_quality_lab.services.reconciliation import (
    SettlementClassification,
    calculate_ledger_totals,
    classify_settlement,
)

NOW = datetime(2026, 8, 19, 5, 0, tzinfo=UTC)


def ledger_entry(
    operation: str,
    amount: int,
    created_at: datetime,
    *,
    suffix: str,
) -> LedgerEntryRecord:
    return LedgerEntryRecord(
        id=f"led_{suffix}",
        payment_id="pay_reconciliation_unit",
        operation=operation,
        amount=amount,
        currency="JPY",
        created_at=created_at,
    )


def settlement_record(
    amount: int,
    currency: str = "JPY",
    *,
    line_number: int = 1,
    suffix: str = "one",
) -> SettlementRecord:
    return SettlementRecord(
        id=f"set_{suffix}",
        batch_id="setb_unit",
        payment_id="pay_reconciliation_unit",
        line_number=line_number,
        amount=amount,
        currency=currency,
        created_at=NOW,
    )


def test_cutoff_includes_entries_at_the_boundary_only() -> None:
    entries = [
        ledger_entry(
            "AUTHORIZATION", 1000, NOW - timedelta(seconds=1), suffix="authorize"
        ),
        ledger_entry("CAPTURE", 1000, NOW, suffix="capture"),
        ledger_entry("REFUND", 250, NOW + timedelta(seconds=1), suffix="refund"),
    ]

    totals = calculate_ledger_totals(entries, cutoff=NOW)

    assert totals.authorized == 1000
    assert totals.captured == 1000
    assert totals.refunded == 0
    assert totals.net_captured == 1000


def test_confirmation_capture_counts_as_authorized_and_captured_once() -> None:
    totals = calculate_ledger_totals(
        [ledger_entry("CONFIRMATION_CAPTURE", 2500, NOW, suffix="confirmation")]
    )

    assert totals.authorized == 2500
    assert totals.captured == 2500
    assert totals.refunded == 0
    assert totals.net_captured == 2500


@pytest.mark.parametrize(
    ("expected_amount", "records", "expected_classification", "observed"),
    [
        (1000, [], SettlementClassification.MISSING, 0),
        (0, [], SettlementClassification.MATCHED, 0),
        (
            1000,
            [settlement_record(1000)],
            SettlementClassification.MATCHED,
            1000,
        ),
        (
            1000,
            [settlement_record(999)],
            SettlementClassification.AMOUNT_MISMATCHED,
            999,
        ),
        (
            1000,
            [settlement_record(1000, "USD")],
            SettlementClassification.AMOUNT_MISMATCHED,
            1000,
        ),
        (
            1000,
            [
                settlement_record(1000, line_number=2, suffix="second"),
                settlement_record(900, line_number=1, suffix="first"),
            ],
            SettlementClassification.DUPLICATED,
            900,
        ),
    ],
)
def test_settlement_classification_rules(
    expected_amount: int,
    records: list[SettlementRecord],
    expected_classification: SettlementClassification,
    observed: int,
) -> None:
    comparison = classify_settlement(
        expected_amount=expected_amount,
        expected_currency="JPY",
        records=records,
    )

    assert comparison.classification is expected_classification
    assert comparison.canonical_observed_amount == observed


@pytest.mark.parametrize(
    ("currency", "amount"),
    [("JPY", 1234), ("USD", 1099)],
)
def test_currency_amounts_remain_exact_in_integer_minor_units(
    currency: str,
    amount: int,
) -> None:
    comparison = classify_settlement(
        expected_amount=amount,
        expected_currency=currency,
        records=[settlement_record(amount, currency)],
    )

    assert comparison.classification is SettlementClassification.MATCHED
    assert comparison.canonical_observed_amount == amount
    assert isinstance(comparison.canonical_observed_amount, int)
