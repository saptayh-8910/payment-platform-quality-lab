"""Explicit database migration and schema-version controls."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

DEFAULT_DATABASE_URL = "sqlite:///payment_lab.db"
MIGRATION_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"


class DatabaseSchemaError(RuntimeError):
    """The database has not been upgraded to the required schema revision."""


def migration_config(database_url: str) -> Config:
    """Build an Alembic configuration without relying on the working directory."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATION_DIRECTORY))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def head_revision() -> str:
    """Return the revision required by this application build."""
    scripts = ScriptDirectory.from_config(migration_config(DEFAULT_DATABASE_URL))
    head = scripts.get_current_head()
    if head is None:  # pragma: no cover - packaging failure guard
        raise RuntimeError("No database migration head is available")
    return head


def current_revision(engine: Engine) -> str | None:
    """Return the revision recorded in one database, if any."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def require_current_schema(engine: Engine) -> None:
    """Stop application startup when an explicit migration is still required."""
    current = current_revision(engine)
    required = head_revision()
    if current != required:
        observed = current or "unversioned"
        raise DatabaseSchemaError(
            "Database schema is not current "
            f"(found {observed}, required {required}). "
            "Run payment-quality-lab-migrate before starting the service."
        )


def upgrade_database(database_url: str) -> str:
    """Upgrade one database to the latest explicit revision."""
    config = migration_config(database_url)
    command.upgrade(config, "head")
    return head_revision()


def run() -> None:
    """Upgrade the configured local database from the command line."""
    database_url = os.getenv("PAYMENT_LAB_DATABASE_URL", DEFAULT_DATABASE_URL)
    revision = upgrade_database(database_url)
    print(f"Database schema is current at revision {revision}.")
