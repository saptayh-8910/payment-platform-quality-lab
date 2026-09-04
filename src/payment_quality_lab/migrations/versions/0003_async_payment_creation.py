"""Add asynchronous-payment creation metadata.

Revision ID: 0003_async_creation
Revises: 0002_legacy_upgrade
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_async_creation"
down_revision: str | None = "0002_legacy_upgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _check_constraint_names(table_name: str) -> set[str | None]:
    inspector = sa.inspect(op.get_bind())
    return {
        constraint["name"] for constraint in inspector.get_check_constraints(table_name)
    }


def _has_unique_payment_reference(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint.get("column_names") == ["payment_reference"]
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _upgrade_payments() -> None:
    columns = _column_names("payments")
    if "payment_flow" not in columns:
        op.add_column(
            "payments",
            sa.Column(
                "payment_flow",
                sa.String(length=32),
                nullable=False,
                server_default="SYNCHRONOUS",
            ),
        )
    if "payment_reference" not in columns:
        op.add_column(
            "payments",
            sa.Column("payment_reference", sa.String(length=36), nullable=True),
        )
    if "expires_at" not in columns:
        op.add_column(
            "payments",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    checks = _check_constraint_names("payments")
    has_unique_reference = _has_unique_payment_reference("payments")
    if (
        "ck_payment_flow_supported" in checks
        and "ck_payment_flow_metadata" in checks
        and has_unique_reference
    ):
        return
    with op.batch_alter_table("payments", recreate="always") as batch_op:
        if "ck_payment_flow_supported" not in checks:
            batch_op.create_check_constraint(
                "ck_payment_flow_supported",
                "payment_flow IN ('SYNCHRONOUS', 'ASYNCHRONOUS_CONFIRMATION')",
            )
        if "ck_payment_flow_metadata" not in checks:
            batch_op.create_check_constraint(
                "ck_payment_flow_metadata",
                "(payment_flow = 'SYNCHRONOUS' "
                "AND payment_reference IS NULL AND expires_at IS NULL) OR "
                "(payment_flow = 'ASYNCHRONOUS_CONFIRMATION' "
                "AND payment_reference IS NOT NULL AND expires_at IS NOT NULL)",
            )
        if not has_unique_reference:
            batch_op.create_unique_constraint(
                "uq_payments_payment_reference", ["payment_reference"]
            )


def _upgrade_merchant_projections() -> None:
    columns = _column_names("merchant_payment_projections")
    if "payment_flow" not in columns:
        op.add_column(
            "merchant_payment_projections",
            sa.Column(
                "payment_flow",
                sa.String(length=32),
                nullable=False,
                server_default="SYNCHRONOUS",
            ),
        )
    if "payment_reference" not in columns:
        op.add_column(
            "merchant_payment_projections",
            sa.Column("payment_reference", sa.String(length=36), nullable=True),
        )
    if "expires_at" not in columns:
        op.add_column(
            "merchant_payment_projections",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def upgrade() -> None:
    """Backfill existing payments as synchronous and add delayed metadata."""
    _upgrade_payments()
    _upgrade_merchant_projections()


def downgrade() -> None:
    """Reject removal because references and expiry evidence may exist."""
    raise RuntimeError(
        "Downgrade is intentionally unsupported because it could discard "
        "asynchronous-payment evidence"
    )
