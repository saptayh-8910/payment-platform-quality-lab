"""Independent database verification for performance runs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from payment_quality_lab.performance.profiles import (
    available_profiles,
    expected_payments,
    idempotency_key,
    reference,
)
from payment_quality_lab.persistence.database import create_database_engine
from payment_quality_lab.persistence.models import (
    IdempotencyRecord,
    LedgerEntryRecord,
    PaymentRecord,
    WebhookEventRecord,
)


@dataclass(frozen=True)
class VerificationCheck:
    """One named financial assertion without record-level sensitive data."""

    name: str
    passed: bool
    expected: object
    observed: object


@dataclass(frozen=True)
class VerificationReport:
    """Sanitized post-load evidence."""

    schema_version: int
    run_id: str
    profile: str
    passed: bool
    checks: tuple[VerificationCheck, ...]
    currency_summary: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _check(name: str, expected: object, observed: object) -> VerificationCheck:
    return VerificationCheck(name, expected == observed, expected, observed)


def _private_check(
    name: str,
    passed: bool,
    *,
    expected_count: int,
    observed_count: int,
) -> VerificationCheck:
    """Report cardinality while keeping compared record values private."""
    return VerificationCheck(name, passed, expected_count, observed_count)


def _currency_summary(
    payments: list[PaymentRecord], ledgers: list[LedgerEntryRecord]
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "payment_count": 0,
            "payment_minor_units": 0,
            "authorized_minor_units": 0,
            "ledger_count": 0,
            "ledger_minor_units": 0,
        }
    )
    for payment in payments:
        currency = summary[payment.currency]
        currency["payment_count"] += 1
        currency["payment_minor_units"] += payment.amount
        currency["authorized_minor_units"] += payment.authorized_amount
    for ledger in ledgers:
        currency = summary[ledger.currency]
        currency["ledger_count"] += 1
        currency["ledger_minor_units"] += ledger.amount
    return dict(sorted(summary.items()))


def _expected_currency_summary(profile: str) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "payment_count": 0,
            "payment_minor_units": 0,
            "authorized_minor_units": 0,
            "ledger_count": 0,
            "ledger_minor_units": 0,
        }
    )
    for payment in expected_payments(profile):
        currency = summary[payment.currency]
        currency["payment_count"] += 1
        currency["payment_minor_units"] += payment.amount
        if payment.approved:
            currency["authorized_minor_units"] += payment.amount
            currency["ledger_count"] += 1
            currency["ledger_minor_units"] += payment.amount
    return dict(sorted(summary.items()))


def verify_database(database_url: str, run_id: str, profile: str) -> VerificationReport:
    """Compare run-scoped database effects with the reviewed profile contract."""
    if profile not in available_profiles():
        raise ValueError(f"Unknown performance profile: {profile}")

    expected = expected_payments(profile)
    expected_references = {
        reference(run_id, profile, payment) for payment in expected
    }
    expected_keys = {
        idempotency_key(run_id, profile, payment) for payment in expected
    }
    reference_prefix = f"perf-{run_id}-{profile}-%"
    key_prefix = f"perf-{run_id}-{profile}-%"
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            payments = list(
                session.scalars(
                    select(PaymentRecord).where(
                        PaymentRecord.merchant_reference.like(reference_prefix)
                    )
                )
            )
            payment_ids = {payment.id for payment in payments}
            ledgers = (
                list(
                    session.scalars(
                        select(LedgerEntryRecord).where(
                            LedgerEntryRecord.payment_id.in_(payment_ids)
                        )
                    )
                )
                if payment_ids
                else []
            )
            idempotency_records = list(
                session.scalars(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.key.like(key_prefix)
                    )
                )
            )
            webhooks = (
                list(
                    session.scalars(
                        select(WebhookEventRecord).where(
                            WebhookEventRecord.payment_id.in_(payment_ids)
                        )
                    )
                )
                if payment_ids
                else []
            )
    finally:
        engine.dispose()

    approved_count = sum(payment.approved for payment in expected)
    status_counts = Counter(payment.status for payment in payments)
    expected_statuses = Counter(
        "AUTHORIZED" if payment.approved else "DECLINED" for payment in expected
    )
    ledger_payment_ids = Counter(entry.payment_id for entry in ledgers)
    expected_ledger_shape = sorted(
        [1] * approved_count + [0] * (len(expected) - approved_count)
    )
    observed_ledger_shape = sorted(
        ledger_payment_ids.get(payment.id, 0) for payment in payments
    )
    payment_by_id = {payment.id: payment for payment in payments}
    valid_initial_payments = sum(
        payment.version == 1
        and payment.captured_amount == 0
        and payment.refunded_amount == 0
        and (
            (
                payment.status == "AUTHORIZED"
                and payment.authorized_amount == payment.amount
            )
            or (payment.status == "DECLINED" and payment.authorized_amount == 0)
        )
        for payment in payments
    )
    matching_ledgers = sum(
        entry.operation == "AUTHORIZATION"
        and entry.payment_id in payment_by_id
        and entry.amount == payment_by_id[entry.payment_id].authorized_amount
        and entry.currency == payment_by_id[entry.payment_id].currency
        for entry in ledgers
    )
    completed_idempotency_records = sum(
        record.operation == "AUTHORIZE"
        and record.payment_id in payment_ids
        and record.response_snapshot is not None
        for record in idempotency_records
    )
    currency_summary = _currency_summary(payments, ledgers)
    expected_currency = _expected_currency_summary(profile)

    checks = (
        _check("payment count", len(expected), len(payments)),
        _private_check(
            "merchant references",
            expected_references
            == {payment.merchant_reference for payment in payments},
            expected_count=len(expected_references),
            observed_count=len({payment.merchant_reference for payment in payments}),
        ),
        _check("payment statuses", dict(expected_statuses), dict(status_counts)),
        _private_check(
            "initial payment values",
            valid_initial_payments == len(expected),
            expected_count=len(expected),
            observed_count=valid_initial_payments,
        ),
        _check("ledger count", approved_count, len(ledgers)),
        _private_check(
            "one ledger effect per approval",
            expected_ledger_shape == observed_ledger_shape,
            expected_count=len(expected_ledger_shape),
            observed_count=len(observed_ledger_shape),
        ),
        _check(
            "ledger operations",
            {"AUTHORIZATION": approved_count},
            dict(Counter(entry.operation for entry in ledgers)),
        ),
        _private_check(
            "ledger values match authorized payments",
            matching_ledgers == approved_count,
            expected_count=approved_count,
            observed_count=matching_ledgers,
        ),
        _check("idempotency count", len(expected), len(idempotency_records)),
        _private_check(
            "completed authorization idempotency records",
            completed_idempotency_records == len(expected),
            expected_count=len(expected),
            observed_count=completed_idempotency_records,
        ),
        _private_check(
            "idempotency keys",
            expected_keys == {record.key for record in idempotency_records},
            expected_count=len(expected_keys),
            observed_count=len({record.key for record in idempotency_records}),
        ),
        _private_check(
            "idempotency payments",
            payment_ids
            == {
                record.payment_id
                for record in idempotency_records
                if record.payment_id is not None
            },
            expected_count=len(payment_ids),
            observed_count=len(
                {
                    record.payment_id
                    for record in idempotency_records
                    if record.payment_id is not None
                }
            ),
        ),
        _check("webhook count", len(expected), len(webhooks)),
        _check(
            "webhook statuses",
            {"PENDING": len(expected)},
            dict(Counter(event.status for event in webhooks)),
        ),
        _check(
            "webhook event types",
            dict(
                Counter(
                    "payment.authorized" if payment.approved else "payment.declined"
                    for payment in expected
                )
            ),
            dict(Counter(event.event_type for event in webhooks)),
        ),
        _private_check(
            "one version-one webhook per payment",
            {(payment_id, 1) for payment_id in payment_ids}
            == {(event.payment_id, event.aggregate_version) for event in webhooks},
            expected_count=len(payment_ids),
            observed_count=len(
                {(event.payment_id, event.aggregate_version) for event in webhooks}
            ),
        ),
        _check("currency totals", expected_currency, currency_summary),
    )
    return VerificationReport(
        schema_version=1,
        run_id=run_id,
        profile=profile,
        passed=all(check.passed for check in checks),
        checks=checks,
        currency_summary=currency_summary,
    )


def write_report(report: VerificationReport, output_path: Path) -> None:
    """Write deterministic, human-readable JSON evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
