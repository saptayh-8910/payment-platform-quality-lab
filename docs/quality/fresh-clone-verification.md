# Final fresh-clone README verification

Date: 2026-09-14. Result: passed with one dependency deprecation warning.
Tested commit: `a16f56ee14764f6ef5beacc0d3c34ddf356bf8f9`, PR #26.

## Purpose and environment

Check that a new checkout can follow the README to install, migrate, start,
and test the completed project. This supplements CI; it does not replace it.

The repository was cloned from GitHub into a new temporary directory, using
branch `codex/e2-milestone-closeout`. A new Python virtual environment and new
Node dependency directory were created. The working project's environment and
database were not reused. Host download caches and the Chromium cache could
be reused; this was not a factory-reset machine test.

Environment: macOS, Python 3.14.7, Node 24.12.0, Chromium via the locked
Playwright dependency, and k6 v2.0.0. The Python installation resolved current
dependencies within the declared ranges, including FastAPI 0.141.1,
Starlette 1.6.0, SQLAlchemy 2.0.52, and Alembic 1.20.0.

## Commands and observed results

Commands were executed from the clean checkout. Explicit `.venv/bin` paths
were used instead of shell activation; they select the same new environment.

| README step | Result |
|---|---|
| `python3 -m venv .venv` | New environment created |
| `.venv/bin/python -m pip install --editable '.[dev]'` | Installation succeeded |
| `.venv/bin/python -m pytest -q` | 397 passed; 85.84% branch-aware coverage |
| `.venv/bin/payment-quality-lab-migrate` | New local database created at `0006_reports` |
| `.venv/bin/payment-quality-lab` | Normal service started on loopback port 8000 |
| Health, API docs, checkout and asynchronous JavaScript asset requests | Successful responses; health returned `ok` |
| Synthetic JPY authorization, capture and partial refund | AUTHORIZED → CAPTURED → PARTIALLY_REFUNDED; captured 2500, refunded 500 |
| `npm ci` | Lockfile installation succeeded; audit reported zero vulnerabilities at execution |
| `npx playwright install chromium` | Completed successfully |
| `npm run test:browser` | 49 Node tests, TypeScript check, 18 Cucumber scenarios and 140 steps passed |
| Performance smoke | Traffic/timing, financial verification and evidence gates passed |

The performance command used `--k6-binary` to select the previously verified
v2.0.0 binary explicitly instead of changing the host PATH. Run ID:
`freshcheck20260914`. This is the existing synchronous smoke workload, not
an asynchronous capacity test.

## Warning and scope

Pytest reported one Starlette test-client deprecation warning: the
`anyio.abc.BlockingPortal` alias is deprecated in favour of
`anyio.from_thread.BlockingPortal`. No test failed. No warning suppression,
dependency change, or application fix was made. Compatibility should be
rechecked during future dependency updates.

No README setup defect was found in this environment. The test does not prove
Windows/Linux manual installation, offline installation, or future dependency
compatibility. CI separately tests the supported Python matrix on its runners.

The temporary service was stopped after verification. Logs, the isolated
database, and generated reports remain local under
`/tmp/payment-fresh.PwCuYE/`; temporary files are not permanent release evidence.
This document records the commands and outcomes; remote CI artifacts and PR
checks provide the separate automated release evidence.

## Release handoff

The tested implementation is unchanged by this documentation update. The
summary and this record are delivered together to PR #26. Verify its latest
checks before owner merge; create the release tag afterward.
