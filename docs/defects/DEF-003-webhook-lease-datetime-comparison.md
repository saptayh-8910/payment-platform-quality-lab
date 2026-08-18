# DEF-003: Webhook dispatch fails during atomic lease acquisition

## Summary

The first webhook dispatcher implementation used SQLAlchemy's default session
synchronization for an atomic lease update. SQLite returned stored timestamps
without timezone information, while the dispatcher clock supplied a timezone-
aware UTC value. SQLAlchemy tried to compare these values in Python and raised
a `TypeError` before delivery started.

## Discovery

- Milestone: M5 webhook delivery and reconciliation
- Found by: webhook delivery integration suite
- Environment: SQLite in memory, SQLAlchemy 2, Python 3.14
- Severity: High
- Status: Resolved in the webhook implementation PR

## Impact

The payment and outbox event were saved correctly, but the dispatcher could not
claim the event. No webhook request was sent and no delivery attempt was
recorded. If released, every ready webhook could remain pending until the lease
code was corrected.

There was no duplicate charge or ledger corruption. The failure was limited to
notification delivery, but a merchant could have an outdated payment view.

## Reproduction

1. Create an authorized payment and its committed webhook event.
2. Ask the dispatcher to deliver the ready event.
3. Let the atomic update compare the stored lease time with the injected UTC
   clock.

Expected: one dispatcher claims the event and starts the first attempt.

Observed: SQLAlchemy raised an error because Python cannot order a timezone-
aware datetime and a timezone-naive datetime.

## Root cause

The SQL update itself was safe for the database. The problem came from the ORM's
default behavior after the update. It tried to evaluate the lease condition
against objects already loaded in the session. SQLite had reconstructed their
timestamps without timezone information, so that local Python comparison was
not valid.

This difference can be easy to miss because both values represent UTC and look
similar when printed.

## Resolution

The lease remains one conditional database update, but ORM-side evaluation is
disabled with `synchronize_session=False`. After the update, the session expires
its cached objects and reloads the state from the database.

The database now decides whether the event is ready and unclaimed. Python does
not repeat the timestamp comparison using values with different timezone
metadata.

## Regression evidence

- `test_successful_delivery_records_attempt_and_projection` confirms that a
  ready event can be claimed and delivered.
- `test_concurrent_dispatchers_create_one_active_attempt` confirms that two
  workers cannot create parallel first attempts for the same event.
- Retry and exhaustion tests confirm that scheduled events can be claimed again
  at later controlled times.
- The focused webhook suite passes on Python 3.14.

## Learning

Database timestamps and application clocks need explicit boundary tests. An
atomic SQL condition should be evaluated by the database when correctness
depends on its stored representation. Concurrency tests should also verify the
result, because removing ORM synchronization must not weaken lease ownership.
