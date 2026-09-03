# Database migrations

## Purpose

The application stores payment, ledger, idempotency, webhook, projection, and
reconciliation evidence in SQLite. A schema change must preserve that evidence
or stop clearly. Creating missing tables is not a safe substitute for upgrading
existing tables.

## Local workflow

Install the current project version, upgrade the configured database, and then
start the service:

```bash
python -m pip install --editable '.[dev]'
payment-quality-lab-migrate
payment-quality-lab
```

Both commands use `sqlite:///payment_lab.db` by default. To use another
database, give both commands the same environment variable:

```bash
export PAYMENT_LAB_DATABASE_URL='sqlite:////absolute/path/payment_lab.db'
payment-quality-lab-migrate
payment-quality-lab
```

Back up a database before applying a migration when its contents matter. The
compatibility migration is designed to preserve known existing records, but a
backup remains the recovery path for an interrupted local machine or storage
failure.

## Safety behavior

- A fresh database is created at the current revision.
- The known unversioned project schema is upgraded and adopted.
- Existing authorization idempotency records receive an operation and an
  immutable response snapshot so equivalent retries still return the original
  result.
- Existing declined payment and merchant-projection records receive the safe
  generic `unknown` reason when the older schema had no reason field.
- An unknown unversioned table or column shape stops migration.
- Starting the HTTP service against an unversioned or outdated database stops
  before the server is ready and names the required migration command.
- Repeating the upgrade command at the current revision is safe.

## Downgrade boundary

The compatibility revision cannot safely downgrade because the older schema
cannot represent lifecycle operation identity or immutable replay snapshots.
Removing those fields would discard evidence and could also reintroduce the old
one-idempotency-record-per-payment restriction. Restore a reviewed backup when
rollback of persisted local data is required.

## Quality evidence

The migration scenarios are listed as `MIG-01` to `MIG-06` and `REG-M01` in the
[Enhancement 2 catalog](quality/enhancements/e2-asynchronous-payment-confirmation/scenario-catalog.md).
The executable upgrade evidence is in
`tests/integration/test_database_migrations.py`. The original discovery is
recorded as [DEF-008](defects/DEF-008-unversioned-local-database.md).
