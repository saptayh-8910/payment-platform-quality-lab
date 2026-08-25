# Milestone 8 Performance Harness Implementation Guide

## Document information

| Field | Value |
|---|---|
| Milestone | 8: Performance baseline and portfolio-ready reporting |
| Status | In progress; harness and CI workflow implemented, closing evidence pending |
| Test basis | [Performance scenario catalog](scenario-catalog.md) |
| Load tool | Grafana k6 OSS v2.0.0 |
| Final decision | Recorded later in the milestone quality report |

## Situation

The functional suites prove that payment behavior is correct under controlled
examples. They do not prove that a declared workload completes at the planned
rate. A normal load test is also not enough for a payment platform. Fast HTTP
responses can still hide a missing ledger entry or a duplicate authorization.

The Milestone 8 harness therefore makes two independent decisions:

1. k6 checks traffic volume, HTTP behavior, dropped work, and response time.
2. A Python verifier checks the resulting payment, ledger, idempotency, and
   webhook records directly in the temporary database.

The overall run passes only when both decisions pass and both sanitized reports
are valid.

## Execution flow

```text
local command
  -> validate the profile, run ID, and pinned k6 version
  -> create a temporary SQLite database and loopback port
  -> start FastAPI with failure injection disabled
  -> wait for the health endpoint
  -> execute the selected k6 profile
  -> run the financial verifier even when a k6 threshold fails
  -> validate both evidence files
  -> stop FastAPI and remove the temporary database
```

The runner creates the target itself. The k6 script also rejects any target
that is not an explicit `http://127.0.0.1:PORT` or
`http://localhost:PORT` origin. There is no command option for remote load.

## Why the responsibilities are separate

k6 is responsible for generating traffic because an arrival-rate executor can
keep the offered rate clear even when a response becomes slower. k6 checks the
status, required response values, exact request count, error rate, dropped
iterations, and p95 and p99 response time.

The Python verifier is separate because k6 virtual users do not share normal
JavaScript memory. Database evidence is also a stronger oracle for financial
side effects. The verifier checks exact run-scoped references and keys in
memory, but it writes only counts and currency totals to the retained report.
Raw keys and database record identifiers are not retained.

The runner is responsible for lifecycle and safety. It uses a fresh file-backed
database for every profile, starts only one local application, and always stops
the child process. The database is removed after verification.

## Workload contracts

| Profile | Measured traffic | Setup or warm-up effects | Expected final financial effects |
|---|---:|---:|---:|
| `smoke` | 5 authorizations and 4 reads | None | 5 payments, 4 ledger entries, 5 idempotency records, 5 webhooks |
| `authorization` | 150 approvals at 5 per second | 5 warm-up approvals | 155 of each persistent approval record |
| `retrieval` | 300 reads at 10 per second | 20 setup approvals and 5 warm-up reads | 20 of each persistent approval record |
| `idempotent-burst` | 20 equivalent concurrent replays | 1 original approval and 1 warm-up replay | 1 payment, ledger entry, idempotency record, and webhook |
| `mixed` | 120 approvals and 480 reads | 20 setup approvals and 5 warm-up reads | 140 of each persistent approval record |

Unique write profiles alternate JPY and USD. The verifier keeps currency counts
and integer minor-unit totals separate. A declined smoke payment has a payment,
idempotency record, and webhook, but it has no ledger effect.

Grafana k6 v2.0.0 can schedule an iteration at the exact closing boundary. The
implementation uses a window just below the rounded 30 or 60 seconds and adds
exact custom counter thresholds. This keeps the catalog volume stable at 150,
300, 120, and 480 measured operations. If the generator starts one extra or one
fewer operation, the run fails.

## Local use

Python 3.12 or newer and the project development dependencies are required.
Use the pinned k6 v2.0.0 standalone binary or an exact local installation.

Run the short end-to-end harness check:

```bash
python scripts/run_performance.py smoke
```

Run one measured profile:

```bash
python scripts/run_performance.py authorization
python scripts/run_performance.py retrieval
python scripts/run_performance.py idempotent-burst
python scripts/run_performance.py mixed
```

Use `--k6-binary /path/to/k6` when the pinned executable is not on `PATH`.
The optional `--run-id` accepts 8 to 24 lowercase letters or digits.

The controlled negative check proves that a threshold failure blocks the run:

```bash
python scripts/run_performance.py smoke --force-threshold-failure
```

This command is expected to exit with failure. The financial verifier still
runs, so the evidence can show that the product state remained correct while
the performance gate was deliberately rejected.

## Automatic business checkpoint

The GitHub Actions workflow turns the local test into a shared release check.
It removes the need to trust that one person remembered to run the right
command. Developers, QA engineers, and product stakeholders can see the same
result and download the same evidence.

| Trigger | Profiles | Business purpose |
|---|---|---|
| Relevant pull request | `smoke` | Catch a broken harness, failed payment response, or incorrect financial effect before merge |
| Manual request | One selected profile or `all` | Support a release decision or focused investigation |
| Tuesday at 03:17 UTC | All five profiles | Give an early warning when performance or reliability changes over time |

Pull-request smoke runs also execute a controlled impossible threshold. The
workflow expects that command to fail, then confirms that k6 recorded a failed
gate while the financial verifier still completed. This proves that a real
threshold failure cannot be reported as success merely because evidence was
uploaded.

The workflow validates the Python harness once, installs the checksum-verified
k6 v2.0.0 Linux binary, inspects each selected script, and runs every selected
profile in an isolated matrix job. A failure in one profile does not cancel the
other profiles.

## Reading the evidence

Each run writes two generated files under
`reports/performance/RUN_ID/PROFILE/`:

- `k6-summary.json` contains the selected profile, exact traffic counters,
  response checks, failures, dropped iterations, and latency values.
- `financial-verification.json` contains expected and observed record counts,
  status counts, event types, and separate JPY and USD totals.

The files must have the same run ID and profile. Evidence validation rejects a
missing or malformed file and scans for raw test tokens, idempotency headers,
database URLs, failure controls, home-directory paths, and workstation names.
Per-request output is not retained.

The `reports/` directory is ignored by Git. Generated local results are useful
for investigation. In GitHub Actions, the same files are uploaded for 14 days,
even when the performance command fails. The job writes a short summary of the
traffic, timing, and financial decisions before it enforces the final result.

These generated files are supporting evidence, not the permanent milestone
decision. The closing quality report will record the reviewed CI environment,
repeated baseline results, limitations, and final recommendation.

## Current boundary

The workflow must be merged before manual and scheduled execution are available
from the default branch. Milestone 8 also remains open until the complete
baseline runs twice from merged code and the closing report explains timing
variation and limitations.

This project does not claim production capacity. FastAPI, k6, and SQLite share
one GitHub-hosted runner, so results are regression guardrails for this
simulator only.
