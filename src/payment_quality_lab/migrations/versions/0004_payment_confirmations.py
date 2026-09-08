"""Add the durable asynchronous-confirmation inbox.

Revision ID: 0004_confirmations
Revises: 0003_async_creation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_confirmations"
down_revision: str | None = "0003_async_creation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create minimal confirmation evidence without changing existing rows."""
    inspector = sa.inspect(op.get_bind())
    if "payment_confirmations" in inspector.get_table_names():
        expected_columns = {
            "confirmation_id",
            "request_fingerprint",
            "payment_reference",
            "amount",
            "currency",
            "received_at",
            "disposition",
            "payment_id",
            "response_snapshot",
        }
        observed_columns = {
            column["name"] for column in inspector.get_columns("payment_confirmations")
        }
        if observed_columns != expected_columns:
            raise RuntimeError(
                "Existing payment_confirmations table has an unsupported shape"
            )
        return
    op.create_table(
        "payment_confirmations",
        sa.Column("confirmation_id", sa.String(length=40), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payment_reference", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("payment_id", sa.String(length=40), nullable=True),
        sa.Column("response_snapshot", sa.Text(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_confirmation_amount_positive"),
        sa.CheckConstraint(
            "currency IN ('JPY', 'USD')",
            name="ck_confirmation_currency_supported",
        ),
        sa.CheckConstraint(
            "disposition IN ("
            "'applied', 'late', 'amount_mismatch', 'currency_mismatch', "
            "'unknown_reference', 'already_resolved')",
            name="ck_confirmation_disposition_supported",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("confirmation_id"),
    )
    op.create_index(
        "ix_payment_confirmations_payment_reference",
        "payment_confirmations",
        ["payment_reference"],
    )
    op.create_index(
        "ix_payment_confirmations_received_at",
        "payment_confirmations",
        ["received_at"],
    )
    op.create_index(
        "ix_payment_confirmations_disposition",
        "payment_confirmations",
        ["disposition"],
    )
    op.create_index(
        "ix_payment_confirmations_payment_id",
        "payment_confirmations",
        ["payment_id"],
    )


def downgrade() -> None:
    """Reject removal because confirmation evidence may be financially relevant."""
    raise RuntimeError(
        "Downgrade is intentionally unsupported because it could discard "
        "payment-confirmation evidence"
    )
