"""Persist receipt separately from final financial processing."""

import sqlalchemy as sa
from alembic import op

revision = "0005_receipts"
down_revision = "0004_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "confirmation_receipts" in sa.inspect(bind).get_table_names():
        columns = {
            column["name"]
            for column in sa.inspect(bind).get_columns("confirmation_receipts")
        }
        if columns != {
            "confirmation_id",
            "request_fingerprint",
            "payment_reference",
            "amount",
            "currency",
            "received_at",
            "completed",
        }:
            raise RuntimeError(
                "Existing confirmation_receipts has an unsupported shape"
            )
    if "confirmation_receipts" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "confirmation_receipts",
            sa.Column("confirmation_id", sa.String(40), primary_key=True),
            sa.Column("request_fingerprint", sa.String(64), nullable=False),
            sa.Column("payment_reference", sa.String(36), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.CheckConstraint("amount > 0", name="ck_receipt_amount_positive"),
            sa.CheckConstraint(
                "currency IN ('JPY', 'USD')", name="ck_receipt_currency"
            ),
        )
        op.create_index(
            "ix_confirmation_receipts_payment_reference",
            "confirmation_receipts",
            ["payment_reference"],
        )
        op.create_index(
            "ix_confirmation_receipts_completed", "confirmation_receipts", ["completed"]
        )
    # Historical final results are complete work; never replay them as pending.
    bind.execute(
        sa.text(
            "INSERT INTO confirmation_receipts "
            "(confirmation_id, request_fingerprint, payment_reference, amount, "
            "currency, received_at, completed) "
            "SELECT c.confirmation_id, c.request_fingerprint, c.payment_reference, "
            "c.amount, c.currency, c.received_at, 1 "
            "FROM payment_confirmations c WHERE NOT EXISTS "
            "(SELECT 1 FROM confirmation_receipts r "
            "WHERE r.confirmation_id = c.confirmation_id)"
        )
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade would discard durable receipt evidence")
