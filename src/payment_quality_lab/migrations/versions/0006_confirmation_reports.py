"""Save confirmation reporting evidence without backdating history."""

import sqlalchemy as sa
from alembic import op

revision = "0006_reports"
down_revision = "0005_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "confirmation_reports" in inspector.get_table_names():
        if {c["name"] for c in inspector.get_columns("confirmation_reports")} != {
            "batch_id",
            "payload",
        }:
            raise RuntimeError("Unsupported confirmation_reports shape")
        return
    op.create_table(
        "confirmation_reports",
        sa.Column(
            "batch_id",
            sa.String(40),
            sa.ForeignKey("settlement_batches.id"),
            primary_key=True,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade would discard saved report evidence")
