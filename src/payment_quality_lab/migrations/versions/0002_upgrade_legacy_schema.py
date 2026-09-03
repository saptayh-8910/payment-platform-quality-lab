"""Upgrade databases created before lifecycle idempotency and decline reasons.

Revision ID: 0002_legacy_upgrade
Revises: 0001_baseline
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002_legacy_upgrade"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _serialize_snapshot(row: Mapping[str, object]) -> str:
    def timestamp(value: object) -> str:
        return value.isoformat() if isinstance(value, datetime) else str(value)

    return json.dumps(
        {
            "amount": row["amount"],
            "authorized_amount": row["authorized_amount"],
            "captured_amount": row["captured_amount"],
            "created_at": timestamp(row["created_at"]),
            "currency": row["currency"],
            "decline_reason": row["decline_reason"],
            "id": row["payment_id"],
            "merchant_reference": row["merchant_reference"],
            "refunded_amount": row["refunded_amount"],
            "status": row["status"],
            "updated_at": timestamp(row["updated_at"]),
            "version": row["version"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _upgrade_payment_decline_reason() -> None:
    if "decline_reason" in _column_names("payments"):
        return

    op.add_column(
        "payments",
        sa.Column("decline_reason", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE payments SET decline_reason = 'unknown' WHERE status = 'DECLINED'"
        )
    )
    with op.batch_alter_table("payments", recreate="always") as batch_op:
        batch_op.create_check_constraint("ck_payment_amount_positive", "amount > 0")
        batch_op.create_check_constraint(
            "ck_payment_authorized_within_amount",
            "authorized_amount >= 0 AND authorized_amount <= amount",
        )
        batch_op.create_check_constraint(
            "ck_payment_captured_within_authorized",
            "captured_amount >= 0 AND captured_amount <= authorized_amount",
        )
        batch_op.create_check_constraint(
            "ck_payment_refunded_within_captured",
            "refunded_amount >= 0 AND refunded_amount <= captured_amount",
        )
        batch_op.create_check_constraint(
            "ck_payment_decline_reason_matches_status",
            "(status = 'DECLINED' AND decline_reason IS NOT NULL AND "
            "decline_reason IN ('insufficient_funds', 'limit_exceeded', "
            "'expired_payment_method', 'verification_failed', "
            "'invalid_payment_method', 'unknown')) OR "
            "(status <> 'DECLINED' AND decline_reason IS NULL)",
        )
        batch_op.create_check_constraint("ck_payment_version_positive", "version >= 1")


def _upgrade_projection_decline_reason() -> None:
    if "decline_reason" in _column_names("merchant_payment_projections"):
        return
    op.add_column(
        "merchant_payment_projections",
        sa.Column("decline_reason", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE merchant_payment_projections SET decline_reason = 'unknown' "
            "WHERE status = 'DECLINED'"
        )
    )


def _upgrade_idempotency_records() -> None:
    columns = _column_names("idempotency_records")
    if {"operation", "response_snapshot"}.issubset(columns):
        return

    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                "SELECT i.key, i.request_fingerprint, i.payment_id, i.created_at, "
                "p.merchant_reference, p.amount, p.currency, p.status, "
                "p.decline_reason, p.authorized_amount, p.captured_amount, "
                "p.refunded_amount, p.version, p.created_at AS payment_created_at, "
                "p.updated_at "
                "FROM idempotency_records AS i "
                "JOIN payments AS p ON p.id = i.payment_id"
            )
        ).mappings()
    )

    op.rename_table("idempotency_records", "idempotency_records_legacy")
    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("payment_id", sa.String(length=40), nullable=True),
        sa.Column("response_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_idempotency_records_payment_id",
        "idempotency_records",
        ["payment_id"],
        unique=False,
    )

    insert = sa.text(
        "INSERT INTO idempotency_records "
        "(key, request_fingerprint, operation, payment_id, "
        "response_snapshot, created_at) "
        "VALUES (:key, :request_fingerprint, 'AUTHORIZE', :payment_id, "
        ":response_snapshot, :created_at)"
    )
    for row in rows:
        snapshot_values = dict(row)
        snapshot_values["created_at"] = row["payment_created_at"]
        bind.execute(
            insert,
            {
                "key": row["key"],
                "request_fingerprint": row["request_fingerprint"],
                "payment_id": row["payment_id"],
                "response_snapshot": _serialize_snapshot(snapshot_values),
                "created_at": row["created_at"],
            },
        )
    op.drop_table("idempotency_records_legacy")


def upgrade() -> None:
    """Bring the known unversioned schema to the current model."""
    _upgrade_payment_decline_reason()
    _upgrade_projection_decline_reason()
    _upgrade_idempotency_records()


def downgrade() -> None:
    """Reject a downgrade that could discard lifecycle idempotency evidence."""
    raise RuntimeError(
        "Downgrade is intentionally unsupported because it would discard "
        "idempotency replay evidence"
    )
