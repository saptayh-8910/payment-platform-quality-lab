"""Frozen, generation-time confirmation evidence through a batch cutoff."""

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from payment_quality_lab.persistence.models import (
    ConfirmationReceiptRecord,
    ConfirmationReportRecord,
    PaymentConfirmationRecord,
    PaymentRecord,
    SettlementBatchRecord,
    WebhookEventRecord,
)
from payment_quality_lab.services.coordination import begin_coordinated_write


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def confirmation_section(
    session: Session,
    batch_id: str,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict:
    """First generation writes once; subsequent reads return exactly saved evidence."""
    begin_coordinated_write(session)
    try:
        saved = session.get(ConfirmationReportRecord, batch_id)
        if saved:
            result = json.loads(saved.payload)
            session.commit()
            return result
        batch = session.get(SettlementBatchRecord, batch_id)
        if batch is None:
            raise LookupError("Settlement batch does not exist")
        generated = clock()
        if generated.tzinfo is None or generated.utcoffset() is None:
            raise ValueError("Report clock must be timezone-aware")
        cutoff = utc(batch.cutoff)
        outcomes = Counter(
            {
                name: 0
                for name in (
                    "pending",
                    "confirmed_on_time",
                    "expired_without_on_time_confirmation",
                    "cancelled_unconfirmed",
                )
            }
        )
        for payment in session.scalars(
            select(PaymentRecord).where(
                PaymentRecord.payment_flow == "ASYNCHRONOUS_CONFIRMATION",
                PaymentRecord.created_at <= cutoff,
            )
        ):
            events = list(
                session.scalars(
                    select(WebhookEventRecord)
                    .where(
                        WebhookEventRecord.payment_id == payment.id,
                        WebhookEventRecord.created_at <= cutoff,
                    )
                    .order_by(WebhookEventRecord.aggregate_version)
                )
            )
            statuses = [
                json.loads(event.payload)["payment"]["status"] for event in events
            ]
            if any(
                status in {"CAPTURED", "PARTIALLY_REFUNDED", "REFUNDED"}
                for status in statuses
            ):
                outcome = "confirmed_on_time"
            elif "CANCELLED" in statuses:
                outcome = "cancelled_unconfirmed"
            elif "EXPIRED" in statuses:
                outcome = "expired_without_on_time_confirmation"
            else:
                outcome = "pending"
            outcomes[outcome] += 1
        dispositions = Counter(
            {
                name: 0
                for name in (
                    "applied",
                    "late",
                    "amount_mismatch",
                    "currency_mismatch",
                    "unknown_reference",
                    "already_resolved",
                )
            }
        )
        anomalies = defaultdict(lambda: [0, 0])
        for record in session.scalars(
            select(PaymentConfirmationRecord).where(
                PaymentConfirmationRecord.received_at <= cutoff
            )
        ):
            dispositions[record.disposition] += 1
            if record.disposition != "applied":
                bucket = anomalies[(record.currency, record.disposition)]
                bucket[0] += 1
                bucket[1] += record.amount
        pending = len(
            list(
                session.scalars(
                    select(ConfirmationReceiptRecord.confirmation_id).where(
                        ConfirmationReceiptRecord.received_at <= cutoff,
                        ConfirmationReceiptRecord.completed.is_(False),
                    )
                )
            )
        )
        result = {
            "cutoff": cutoff.isoformat(),
            "generated_at": utc(generated).isoformat(),
            "basis": "effective_through_cutoff_known_at_generation",
            "payment_count": sum(outcomes.values()),
            "payment_outcomes": dict(outcomes),
            "dispositions": dict(dispositions),
            "pending_receipt_count": pending,
            "observed_anomalies": [
                {
                    "currency": currency,
                    "disposition": disposition,
                    "count": values[0],
                    "observed_amount": values[1],
                }
                for (currency, disposition), values in sorted(anomalies.items())
            ],
            "amount_notice": (
                "Observed anomaly amounts are not money received "
                "and are excluded from settlement totals."
            ),
        }
        session.add(
            ConfirmationReportRecord(
                batch_id=batch_id, payload=json.dumps(result, sort_keys=True)
            )
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
