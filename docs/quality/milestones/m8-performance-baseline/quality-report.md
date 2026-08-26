# Milestone 8 Performance Baseline Quality Report

## Document information

| Field | Value |
|---|---|
| Milestone | 8: Performance baseline and portfolio-ready reporting |
| Result | Proceed with documented limitations |
| Tested commit | `213b6411c9e590aed27b939016d5bde04d166761` on `main` |
| Implementation pull requests | [PR #12](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/12) and [PR #13](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/13) |
| Complete passing runs | [Run 32947429733](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32947429733) and [Run 32948122600](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32948122600) |
| Investigated variation | [Run 32947684201](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32947684201) and [confirmation run 32947945877](https://github.com/saptayh-8910/payment-platform-quality-lab/actions/runs/32947945877) |
| Execution date | 2026-08-26 |

## Executive summary

Milestone 8 established a small, repeatable performance baseline for the
payment simulator. The complete workload passed twice on the same merged commit.
Every intended request ran, no HTTP request failed, no iteration was dropped,
and every post-run financial check passed.

The work also produced useful negative evidence. The second complete execution
failed the authorization p99 timing guardrail. Its p99 was 1,588.51 ms against
the limit of 1,000 ms. The payment records were still correct. A focused
authorization confirmation passed, and the next complete execution passed
without changing code or thresholds.

This variation is recorded instead of being hidden. It shows why a shared CI
runner should be used as a regression signal, not as proof of production
capacity. It also proves that a timing failure blocks the workflow while the
financial verifier still completes and preserves evidence.

The recommendation is to proceed with documented limitations. The simulator
met its declared baseline and kept exact financial results under the tested
load. The evidence does not describe a production payment service, distributed
infrastructure, or maximum capacity.

## Situation

Earlier milestones proved correct payment behavior through unit, API,
integration, browser, and exploratory tests. Those tests could not answer two
remaining questions:

1. Can a declared workload finish without errors or dropped work?
2. Does the database remain financially correct after concurrent activity?

A speed-only result was not enough. A payment endpoint could be fast while
creating duplicate payments, missing ledger entries, or combining currencies.
The baseline therefore needed independent traffic and financial decisions.

## Why this risk mattered

Slow payment responses can cause customers or clients to retry. An unsafe retry
can create more than one financial effect. A dropped request can also make a
performance graph look better because the system did less work than planned.

For this reason, the release decision checked latency, offered workload,
response behavior, and stored financial effects together. A run could not pass
only because its average response time looked fast.

## Quality approach

The milestone used four connected controls:

- k6 generated fixed authorization, retrieval, idempotent-retry, and mixed
  workloads. Constant arrival rates made dropped work visible.
- A loopback-only runner created one temporary FastAPI process and SQLite
  database for each profile. It rejected remote targets and cleaned up after
  success or failure.
- An independent Python verifier compared payments, ledger entries,
  idempotency records, webhooks, statuses, references, and currency totals after
  load.
- GitHub Actions enforced thresholds, retained sanitized reports for 14 days,
  and kept running other profiles when one matrix job failed.

The planned workloads and reasons are recorded in the
[scenario catalog](scenario-catalog.md). The repeatable commands and evidence
format are recorded in the [implementation guide](implementation-guide.md).

## Environment and workload

| Item | Executed value |
|---|---|
| Source | Merged `main` commit `213b6411c9e590aed27b939016d5bde04d166761` |
| CI environment | GitHub-hosted `ubuntu-24.04`, Ubuntu 24.04.4 LTS |
| Application runtime | CPython 3.14.7 |
| Load tool | Grafana k6 OSS v2.0.0, checksum verified by the workflow |
| Application | One loopback FastAPI process per profile |
| Database | One temporary file-backed SQLite database per profile |
| Test data | Deterministic synthetic JPY and USD values; no real payments or cardholder data |

The complete workflow executed these profiles:

| Profile | Measured workload |
|---|---|
| `smoke` | Five authorizations, including one decline, and four retrievals |
| `authorization` | 150 unique authorizations at 5 iterations per second |
| `retrieval` | 300 reads at 10 iterations per second after controlled setup |
| `idempotent-burst` | 20 concurrent replays of one original request and key |
| `mixed` | 120 authorizations and 480 retrievals over 60 seconds |

## Repeated timing evidence

The table reports operation-specific p95 and p99 values in milliseconds. The
smoke profile is an execution check and is not used as the main timing baseline.

| Profile and operation | Guardrail p95 / p99 | Passing run 1 | Passing run 2 |
|---|---:|---:|---:|
| Authorization | `<500 / <1000` | 10.15 / 13.25 | 6.90 / 25.54 |
| Retrieval | `<250 / <500` | 2.43 / 2.58 | 2.74 / 2.87 |
| Idempotent replay | `<750 / <1500` | 43.75 / 45.59 | 79.22 / 80.15 |
| Mixed authorization | `<500 / <1000` | 10.35 / 16.12 | 10.16 / 12.43 |
| Mixed retrieval | `<250 / <500` | 6.48 / 7.39 | 6.28 / 7.33 |

Both passing runs had a zero HTTP failure rate and zero dropped iterations for
every profile. The exact sanitized values are also available in the committed
[example baseline summary](example-summary.json).

## Investigated timing variation

The first complete run passed. The next complete run produced a different
authorization result:

| Evidence | Authorization p50 | p95 | p99 | Maximum | Decision |
|---|---:|---:|---:|---:|---|
| First complete run | 7.55 ms | 10.15 ms | 13.25 ms | 17.99 ms | Pass |
| Failed complete run | 52.56 ms | 470.07 ms | 1,588.51 ms | 1,829.25 ms | Fail: p99 exceeded 1,000 ms |
| Focused confirmation | 7.79 ms | 426.86 ms | 761.33 ms | 974.55 ms | Pass |
| Final complete run | 6.12 ms | 6.90 ms | 25.54 ms | 223.25 ms | Pass |

The failed run completed all 150 measured authorizations. It had no failed HTTP
request, no dropped iteration, and no incorrect financial check. The same code
and thresholds then passed in the focused confirmation and the final complete
run.

The evidence is consistent with temporary shared-runner variation, but it does
not prove the exact infrastructure cause. No threshold was weakened. The weekly
workflow remains the right control for detecting whether this pattern becomes
repeated rather than isolated.

## Financial and privacy evidence

Each complete run executed 17 named financial checks for each of five profiles.
All 85 checks passed in each passing run. They confirmed:

- exact payment, ledger, idempotency, and webhook counts;
- one intended financial effect for the concurrent retry burst;
- no write side effect during retrieval load;
- expected payment and webhook statuses;
- equal payment and ledger values; and
- separate and exact JPY and USD counts and minor-unit totals.

The failed timing run also passed all 85 financial checks. This distinction is
important: the service was too slow for one timing guardrail, but it did not
lose or duplicate financial data.

Every retained pair of reports passed the automated evidence validator. The
validator checked the run ID and profile, parsed both files, and rejected raw
test tokens, idempotency headers, database URLs, failure controls, secrets,
temporary paths, home-directory paths, hostnames, and workstation details.

## CI and release-gate evidence

| Evidence | Result |
|---|---|
| PR smoke workflow | Passed in PR #13 |
| Performance harness formatting and lint | Passed |
| Performance harness unit tests | Passed |
| Controlled impossible threshold | Failed as intended, while the financial verifier passed |
| First complete `all` execution | Passed all five profiles |
| Second observed `all` execution | Four profiles passed; authorization timing gate failed and retained evidence |
| Focused authorization confirmation | Passed without code or threshold changes |
| Final complete `all` execution | Passed all five profiles |
| Evidence retention | Five sanitized artifacts per complete run, retained for 14 days |
| Existing project CI | Python 3.12, Python 3.14, and Chromium acceptance jobs passed in PR #13 |

## Defects and observations

No functional or financial product defect was found in this milestone. The
authorization timing failure is recorded as an execution observation rather
than a numbered defect because it did not reproduce consistently on the same
commit and no incorrect application behavior was identified.

If later weekly runs show the same high tail repeatedly, the next investigation
should collect temporary diagnostic timing, operating-system scheduling, and
SQLite transaction evidence. That additional detail should not be retained by
default because the compact reports are intentionally privacy-safe.

## Manual or exploratory evidence

This milestone did not require a new browser exploratory charter. Human review
focused on the CI summaries, downloaded JSON artifacts, timing variation,
financial checks, and privacy fields. The automated workflow was repeatable,
while the human decision explained why one failed timing result could not be
ignored or treated as a financial defect.

## Limitations

- The results are regression guardrails for this simulator, not production
  service-level objectives or a capacity claim.
- FastAPI, k6, and SQLite ran on isolated GitHub-hosted runners. They do not
  represent distributed services, managed databases, network hops, or regional
  failover.
- Shared-runner timing varied significantly during one authorization profile.
- The workload is intentionally modest and lasts at most 60 seconds. It is not
  a soak, stress, spike, or maximum-capacity test.
- Capture, cancellation, refund, webhook dispatch, and reconciliation are
  covered functionally but are not separate throughput profiles.
- Chromium is the only required browser, and browser rendering was not measured
  as part of this API baseline.
- All values and outcomes are synthetic. No real payment method or customer data
  was used.
- No external payment-provider sandbox was called.

## Release recommendation

Proceed with documented limitations. Two complete runs on merged code met every
timing and correctness guardrail. The observed failure was investigated, the
gate behaved correctly, financial evidence remained exact, and repeat execution
passed without weakening the agreed limits.

Milestone 8 and the initial eight-milestone portfolio build can close after the
closeout pull request passes the normal project CI.

## Next quality risks

The first post-MVP enhancement should map selected public payment-provider test
behaviors to the independent simulator. It should use semantic synthetic
outcomes, cite the source and review date, and clearly avoid claiming a real
provider integration. Useful gaps include detailed decline reasons, 3-D Secure
outcomes, interrupted wallet redirects, backend status confirmation, and
preauthorization reversal.

Any provider sandbox integration should remain optional, low volume, and
secret-backed. Performance traffic must continue to target only the controlled
local simulator unless an external provider gives explicit authorization.
