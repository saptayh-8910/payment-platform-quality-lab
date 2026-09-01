# DEF-007: Declined payment accepted without a reason

## Summary

The first Enhancement 1 database constraint allowed a `DECLINED` payment whose
`decline_reason` was `NULL`. The application service always supplied a reason,
but a direct or faulty database write could still create an incomplete record.

## Severity

High.

The payment would have no financial effect, but support, webhook, and customer
guidance could no longer explain why it was declined. This broke an approved
data invariant and could make different system views disagree.

## How it was found

An integration test wrote invalid payment combinations directly to a fresh
SQLite database. The cases with an unknown reason and a reason on an authorized
payment were rejected. The case with `status = 'DECLINED'` and
`decline_reason = NULL` unexpectedly committed.

## Root cause

The original SQL check used this shape:

```sql
status = 'DECLINED' AND decline_reason IN (...)
```

In SQL, comparing `NULL` with the allowed list does not return `FALSE`. It
returns `UNKNOWN`. SQLite treats a check expression as failed only when the
result is false, so the incomplete row passed the constraint.

## Resolution

The declined branch now requires both conditions:

```sql
status = 'DECLINED'
AND decline_reason IS NOT NULL
AND decline_reason IN (...)
```

The other branch continues to require `decline_reason IS NULL` for every
non-declined status.

## Regression evidence

`tests/integration/test_decline_outcomes_persistence.py` checks three invalid
combinations:

- declined payment with no reason;
- declined payment with an unrecognized reason; and
- authorized payment with a decline reason.

All three must raise a database integrity error. The full suite passed after the
constraint was corrected.

## Status

Resolved before the Enhancement 1 pull request was opened.
