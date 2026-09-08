"""Adopt an empty, current, or known legacy database.

Revision ID: 0001_baseline
Revises: None
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

from payment_quality_lab.persistence.models import Base

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWN_LEGACY_MISSING_COLUMNS = {
    "payments": {
        "decline_reason",
        "payment_flow",
        "payment_reference",
        "expires_at",
    },
    "idempotency_records": {"operation", "response_snapshot"},
    "merchant_payment_projections": {
        "decline_reason",
        "payment_flow",
        "payment_reference",
        "expires_at",
    },
}
KNOWN_LEGACY_MISSING_TABLES = {"payment_confirmations"}


def upgrade() -> None:
    """Create a new schema or adopt only the known pre-migration schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names()) - {"alembic_version"}
    expected_tables = set(Base.metadata.tables)

    if not existing_tables:
        Base.metadata.create_all(bind=bind)
        return

    missing_tables = expected_tables - existing_tables
    unsupported_missing = missing_tables - KNOWN_LEGACY_MISSING_TABLES
    if unsupported_missing or existing_tables - expected_tables:
        missing = sorted(missing_tables)
        unexpected = sorted(existing_tables - expected_tables)
        raise RuntimeError(
            "Unsupported unversioned database tables: "
            f"missing={missing}, unexpected={unexpected}"
        )

    for table_name in sorted(existing_tables):
        expected_columns = {
            column.name for column in Base.metadata.tables[table_name].columns
        }
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = expected_columns - existing_columns
        unexpected_columns = existing_columns - expected_columns
        allowed_missing = KNOWN_LEGACY_MISSING_COLUMNS.get(table_name, set())
        if missing_columns - allowed_missing or unexpected_columns:
            raise RuntimeError(
                f"Unsupported unversioned schema for {table_name}: "
                f"missing={sorted(missing_columns)}, "
                f"unexpected={sorted(unexpected_columns)}"
            )


def downgrade() -> None:
    """Remove the complete baseline schema when explicitly requested."""
    Base.metadata.drop_all(bind=op.get_bind())
