# Milestone 8 Performance Baseline Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Milestone | 8: Performance baseline and portfolio-ready reporting |
| Status | Complete; executed results are recorded separately |
| Owner | Sapta Y Husain |
| Planned delivery | Catalog merged, followed by separate implementation, CI evidence, and project closeout PRs |
| Test basis | [Risk-based test plan](../../../test-plan.md), [payment requirements](../../../payment-requirements.md), and [Milestone 7 quality report](../m7-exploratory-testing/quality-report.md) |
| Planned tool | Grafana k6 OSS against a controlled local FastAPI process |
| Closing evidence | [Quality report](quality-report.md) and [sanitized example summary](example-summary.json) |

## Executive summary

Milestone 8 will establish a small, repeatable performance baseline for payment
authorization, retrieval, and concurrent idempotent retry. It will measure
traffic, error rate, latency, dropped work, and financial side effects.

The main risk is not only that an endpoint becomes slow. A payment service can
respond quickly while creating a duplicate payment, losing a ledger entry, or
returning inconsistent results under concurrency. The performance workflow must
therefore combine k6 measurements with database and API verification.

The proposed timing thresholds are engineering guardrails for this simulator.
They are not production service-level objectives. The application and load
generator will share one GitHub Actions runner, use one FastAPI process, and use
SQLite. These limits make the result useful for detecting large regressions,
but they do not predict a distributed production payment platform.

No scenario in this document is passed evidence. Results belong in the closing
quality report after the scripts, verifier, workflow, and repeated baseline runs
have completed.

## Situation

Milestones 2 to 7 proved financial behavior through unit, API, integration,
browser, and exploratory testing. Those checks answer whether the platform does
the correct thing. They do not show whether a small expected workload completes
within an agreed time or whether concurrent retries preserve one effect.

Performance testing introduces its own failure modes. A poorly controlled test
can overload the wrong environment, reuse data accidentally, hide dropped
iterations, compare unrelated machines, or report attractive latency while the
database contains duplicate effects. This milestone must test both the service
and the test harness.

## Quality objectives

- Measure authorization and retrieval latency at a declared request rate.
- Fail when a request, response check, or scheduled iteration is lost.
- Prove that concurrent equivalent retries return one payment result.
- Verify payment, ledger, idempotency, and webhook counts after load.
- Keep JPY and USD data exact and separate in evidence.
- Produce a small human-readable report and a machine-readable JSON summary.
- Run only against an isolated loopback application and temporary database.
- Keep short pull-request feedback separate from longer baseline execution.
- Explain environment limits and normal variation in plain English.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| Concurrent retries create more than one financial effect | Duplicate authorization and customer or merchant loss | Critical |
| Load causes payment, ledger, idempotency, or webhook records to disagree | Financial investigation cannot trust the platform records | Critical |
| Requests fail while aggregate latency still looks acceptable | A summary hides customer-visible errors | High |
| The generator cannot start all planned iterations | The reported rate is lower than the claimed workload | High |
| Authorization latency grows beyond the agreed guardrail | Checkout completion becomes slow or times out | Medium |
| Retrieval latency grows beyond the agreed guardrail | Customer and support result checks become slow | Medium |
| A shared runner produces noisy timing differences | A normal change is rejected or a regression is missed | Medium |
| A script targets a remote or production-like address by mistake | Unapproved traffic or data is created | Critical |
| Reports expose a token, local path, database URL, or failure control | Privacy or security boundary is weakened | High |
| A broken test harness reports success | Reviewers trust evidence that was never measured | High |

## Scope

### Included

- `POST /payments` with unique approved JPY and USD requests.
- `GET /payments/{payment_id}` using a prepared synthetic payment pool.
- A concurrent burst of equivalent authorization retries using one key.
- A small mixed workload with authorization and retrieval running together.
- k6 built-in traffic, error, latency, iteration, and dropped-iteration metrics.
- Custom operation tags and business checks.
- Post-run database verification of financial side effects.
- A short pull-request smoke profile.
- Manually triggered and scheduled baseline profiles.
- JSON, console, and plain-English result evidence.
- Failure-path checks for thresholds, startup, summary parsing, and cleanup.

### Outside scope

- Production capacity, horizontal scaling, or multi-region behavior.
- A real payment processor, bank, customer, or production endpoint.
- Internet or wide-area network latency.
- Browser rendering and Core Web Vitals.
- Sustained soak tests longer than a few minutes.
- Stress testing until the application or runner fails.
- Capture, cancellation, refund, webhook delivery, and reconciliation throughput.
- Database engines other than the local SQLite implementation.
- Grafana Cloud k6, paid monitoring, dashboards, or alerting.
- A claim that one GitHub-hosted runner represents production hardware.

The excluded lifecycle operations already have functional and concurrency
coverage. Adding every operation to this compact baseline would increase run
time without improving the main performance story.

## Tooling basis

The design uses current k6 concepts:

- [Scenarios and executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/)
  separate fixed-iteration, constant virtual-user, and constant-arrival-rate
  workloads.
- [Built-in metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/)
  provide request count, request failure rate, and request duration.
- [Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
  turn agreed metrics into a non-zero process result when a gate fails. Checks
  alone do not fail a k6 run unless the checks metric has a threshold.
- [Dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/)
  reveal when the generator or service cannot start the declared workload.
- [Custom summaries](https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/)
  allow one reviewed JSON summary without retaining every request sample.
- [Automated performance testing](https://grafana.com/docs/k6/latest/testing-guides/automated-performance-testing/)
  supports separate pull-request, scheduled, and manual execution decisions.

The implementation will use k6 OSS locally. It will not upload results or data
to Grafana Cloud.

## Proposed workload model

### Terms

A virtual user, or VU, is one independent k6 worker. A constant arrival rate
starts a declared number of iterations per time unit, even when earlier
iterations are still running. This helps the test describe offered traffic
instead of allowing a slow service to silently reduce the request rate.

### Profiles

| Profile | Workload | Planned volume | Purpose | Normal trigger |
|---|---|---:|---|---|
| `smoke` | One VU performs four approved authorization-and-retrieval journeys plus one decline | 5 writes and 4 reads | Prove script, target, response checks, summary, verifier, and cleanup work | Relevant pull requests |
| `authorization` | Constant arrival rate of 5 unique authorizations each second for 30 seconds | 150 writes | Establish approved-payment write baseline | Manual and scheduled |
| `retrieval` | Constant arrival rate of 10 reads each second for 30 seconds from a prepared pool | 300 reads | Establish stored-payment read baseline | Manual and scheduled |
| `idempotent-burst` | Setup creates one payment, then 20 VUs replay its request and key together | 1 setup write, 20 replay requests, and 1 intended effect | Prove safe retry under a short concurrency burst | Manual and scheduled |
| `mixed` | 2 unique authorizations and 8 retrievals each second for 60 seconds | 120 writes and 480 reads | Observe write/read interaction at a modest steady load | Scheduled or explicit manual run |

The numbers are intentionally small. The purpose is a stable portfolio baseline,
not a maximum-capacity claim. A later change to rate, duration, or concurrency
requires a reviewed catalog update so results are not compared across different
workloads without explanation.

### Warm-up and measurement

Each measured profile will first run a short warm-up that is excluded from the
tagged release thresholds. The report will identify warm-up and measured
samples separately. Setup time, server startup, and database preparation will
not be presented as endpoint latency.

### Currency and outcomes

Unique authorization workloads will alternate JPY and USD. Amounts remain
integer minor units. The measured write baseline will use the approved synthetic
outcome so every intended write has payment, ledger, idempotency, and webhook
evidence. Decline remains in the smoke profile as a response-contract check, but
it will not be mixed into the authorization latency baseline.

## Proposed thresholds

### Hard correctness gates

These gates apply immediately. They are not calibrated from a fast result.

| Metric or evidence | Proposed threshold | Reason |
|---|---|---|
| k6 response checks | `rate==1` | Every expected status and required response field must pass |
| HTTP request failures | `rate==0` | The declared baseline has no error budget for a failed local request |
| Dropped iterations | `count==0` | The full offered workload must start |
| Unique authorization effects | Exact expected payment, ledger, idempotency, and webhook counts | Fast responses cannot hide missing or duplicate records |
| Idempotent burst | 20 replay responses return the setup payment ID; database contains one payment, ledger entry, idempotency record, and webhook event | Equivalent retries must create one financial effect |
| Retrieval side effects | No new financial record is created | A read operation must remain read-only |
| Currency evidence | JPY and USD counts and totals remain separate | No invalid cross-currency total is allowed |
| Summary and verifier | Both files exist, parse, and report the same run ID and profile | Partial evidence must fail the workflow |

### Timing guardrails

| Operation | p95 | p99 | Applies to |
|---|---:|---:|---|
| Unique authorization | Less than 500 ms | Less than 1,000 ms | `authorization` and tagged writes in `mixed` |
| Payment retrieval | Less than 250 ms | Less than 500 ms | `retrieval` and tagged reads in `mixed` |
| Equivalent idempotent retry | Less than 750 ms | Less than 1,500 ms | `idempotent-burst` |

These are proposed regression guardrails, not production promises. They are
deliberately wider than expected loopback timings because GitHub-hosted runner
performance varies. The first implementation run must record observed p50, p95,
p99, maximum, request rate, and environment details. If the guardrails are
changed after calibration, the pull request must explain why before the catalog
is approved.

Average latency will be reported but will not be the primary gate. Averages can
hide a slow tail that affects a smaller group of customers.

## Test data and isolation

- Every run creates a unique synthetic run ID.
- References and idempotency keys include the run ID, profile, VU, and iteration.
- No reference contains a person, email, address, card number, or account value.
- Unique-write profiles never reuse a key accidentally.
- The idempotent burst reuses exactly one key and one immutable request on
  purpose.
- The application starts on an available loopback port.
- The application uses one temporary file-backed SQLite database per profile.
- The database is available to the post-run verifier and removed after evidence
  is complete.
- The k6 target guard accepts only `127.0.0.1` or `localhost` HTTP URLs.
- There is no override for a remote target in this repository workflow.
- Failure injection remains disabled because the performance baseline measures
  normal service behavior.

## Metrics and reporting

### Required k6 metrics

| Metric | Meaning in this milestone |
|---|---|
| `http_reqs` | Number of HTTP requests generated |
| `http_req_failed` | Rate of HTTP requests that k6 considers failed |
| `http_req_duration` | Request sending, server waiting, and response receiving time |
| `checks` | Rate of business response checks that passed |
| `iterations` | Number of workload iterations completed |
| `dropped_iterations` | Iterations that could not start under the declared executor |
| `vus` and `vus_max` | Active and available virtual-user capacity |

Requests will carry low-cardinality tags such as `operation`, `profile`,
`currency`, and `outcome`. Payment IDs, references, keys, and run IDs must not be
metric tags because each unique value would create unnecessary metric series and
could leak evidence details.

### Retained evidence

| Evidence | Format | Retention |
|---|---|---|
| k6 end-of-test summary | Sanitized JSON produced by `handleSummary()` | GitHub Actions artifact for 14 days |
| Financial verifier result | Sanitized JSON with expected and observed counts | GitHub Actions artifact for 14 days |
| Workflow console summary | Short Markdown or plain text | GitHub Actions run log |
| Milestone closing report | Plain-English Markdown | Committed permanently |

Granular per-request JSON will not be retained by default. It is larger, may
contain unnecessary metadata, and is not needed for the baseline decision. A
temporary diagnostic run may enable it locally, but it must be reviewed before
upload.

Reports must not contain raw synthetic API tokens, idempotency keys, database
URLs, signing secrets, failure-control headers, temporary absolute paths, or
workstation names.

## Scenario summary

| ID | Situation | Expected result | Priority | Level | Automation |
|---|---|---|---|---|---|
| `ENV-01` | Script receives a loopback target | Test starts against the isolated application | Critical | Harness | k6 guard |
| `ENV-02` | Script receives a remote, HTTPS, empty, or malformed target | Test stops before sending any request | Critical | Harness | k6 guard test |
| `SMK-01` | One VU performs four approved authorization-and-retrieval journeys | Every response check passes and exact financial records exist | High | Performance smoke | k6 plus verifier |
| `SMK-02` | One synthetic decline is included in smoke | Decline is returned without a ledger effect and with one webhook event | Medium | Performance smoke | k6 plus verifier |
| `AUTH-01` | Unique JPY and USD authorizations arrive at 5 iterations per second | 150 iterations start and finish with no request failure | High | Performance | k6 |
| `AUTH-02` | Authorization baseline finishes | p95 and p99 meet the proposed guardrails | Medium | Performance | k6 thresholds |
| `AUTH-03` | Authorization records are verified after load | Payment, ledger, idempotency, and webhook counts equal intended approvals | Critical | Integration verifier | Python verifier |
| `GET-01` | Prepared payments are retrieved at 10 iterations per second | 300 reads complete with no failed or dropped iteration | High | Performance | k6 |
| `GET-02` | Retrieval baseline finishes | p95 and p99 meet the proposed guardrails | Medium | Performance | k6 thresholds |
| `GET-03` | Retrieval records are compared before and after load | No payment, ledger, idempotency, or webhook count changes | Critical | Integration verifier | Python verifier |
| `IDM-01` | Setup creates a payment, then 20 VUs replay the same request and key together | All replay responses return the setup payment ID | Critical | Performance and reliability | k6 |
| `IDM-02` | Idempotent burst records are verified | Exactly one payment, ledger entry, idempotency record, and webhook event exist | Critical | Integration verifier | Python verifier |
| `IDM-03` | Equivalent replay latency is measured | p95 and p99 meet the wider retry guardrail | Medium | Performance | k6 threshold |
| `MIX-01` | Writes and reads run together for 60 seconds | Both offered rates complete without error or dropped work | High | Performance | k6 scenarios |
| `MIX-02` | Mixed profile completes | Tagged read and write latency meet their own guardrails | Medium | Performance | k6 thresholds |
| `CUR-01` | JPY and USD writes share the baseline | Counts and minor-unit totals remain separated and exact | High | Verifier | Python verifier |
| `EVD-01` | Successful run completes | Sanitized k6 and financial JSON evidence share the run ID and profile | High | Reporting | Automated report check |
| `EVD-02` | Summary is missing, malformed, or from another run | Workflow fails instead of publishing partial evidence | High | Reporting | Automated negative test |
| `GATE-01` | A controlled impossible threshold is selected in harness-test mode | k6 exits non-zero and the wrapper reports the failed metric | High | Harness test | Automated negative test |
| `GATE-02` | Application cannot become healthy | Load is not started and cleanup still runs | High | Harness test | Automated negative test |
| `SAFE-01` | Generated evidence is scanned | No secret, raw token, key, database URL, or local absolute path is present | High | Privacy | Automated scan plus review |
| `CI-01` | Performance files change in a pull request | Syntax, harness tests, and the short smoke profile run | High | CI | GitHub Actions |
| `CI-02` | Baseline workflow is manually triggered | Selected profile runs with reports and threshold gates | High | CI | `workflow_dispatch` |
| `CI-03` | Weekly baseline runs on merged `main` | Complete baseline evidence is retained and failures remain visible | Medium | CI | Scheduled GitHub Actions |

## Detailed centerpiece scenario

### IDM-01 and IDM-02: concurrent equivalent retry burst

#### Business risk

A client may retry when a response is slow. Several application workers may
send the same retry together. If each request creates its own authorization, a
customer could be charged more than once. A latency-only test would miss this
financial failure.

#### Preconditions

- A fresh temporary database and loopback FastAPI process are healthy.
- The application has failure injection disabled.
- Setup has created one payment and returned its synthetic request,
  idempotency key, and payment ID to the VUs.
- The expected starting count for the run ID is zero.

#### Steps

1. Create the original authorization once during setup.
2. Hold the VUs until the idempotent-burst scenario starts.
3. Let each VU send the original authorization request and key once.
4. Check that every response is an idempotent replay of the setup payment ID.
5. Check that every response contains the same financial values.
6. Retrieve the returned payment and ledger through the API.
7. After k6 finishes, inspect payment, ledger, idempotency, and webhook records
   for the run ID.
8. Write expected and observed counts to the financial verifier report.

#### Expected result

- All 20 requests complete without an HTTP or business-check failure.
- Every response identifies the same authorized payment.
- Exactly one payment exists.
- Exactly one authorization ledger entry exists.
- Exactly one completed idempotency record exists.
- Exactly one version-1 webhook event exists.
- The wider retry latency guardrail passes.
- No secret, key, or raw API token appears in retained evidence.

#### Planned evidence

- Tagged k6 latency, check, failure, iteration, and VU metrics.
- Sanitized k6 JSON summary.
- Sanitized financial verifier JSON.
- Focused automated verifier tests using a temporary database.
- GitHub Actions artifact and plain-English closing report.

## Test architecture

The implementation should keep responsibilities separate:

```text
workflow or local runner
  -> start isolated FastAPI process and database
  -> wait for loopback health check
  -> run selected k6 profile
  -> stop load even when a threshold fails
  -> verify database financial effects
  -> scan and publish sanitized summaries
  -> stop application and remove temporary data
```

- k6 owns traffic generation, response checks, timing metrics, and thresholds.
- A small runner owns process startup, profile selection, evidence paths, and
  cleanup.
- A Python verifier owns database count and financial-effect assertions.
- GitHub Actions owns triggers, tool installation, exit-code enforcement, and
  artifact retention.

The verifier must run even if a k6 timing threshold fails, because a slow run
may still contain important financial evidence. The final workflow result fails
when either k6 or the verifier fails.

## CI and release policy

### Pull-request job

Relevant performance or harness changes run unit checks plus the `smoke`
profile. This job proves that the scripts execute and the correctness gates work.
Its short timing values are recorded but are not used as the main baseline.

### Manual baseline

`workflow_dispatch` allows a reviewer to choose `authorization`, `retrieval`,
`idempotent-burst`, `mixed`, or `all`. The selected profile keeps its real
threshold exit status and uploads evidence even after failure.

### Scheduled baseline

A weekly run on merged `main` executes the complete profile set. It provides a
comparable history on the same runner family without delaying every pull
request. A failed scheduled run is evidence to investigate; it does not prove a
product regression until the same commit and profile are repeated.

### Release decision

Milestone 8 cannot close until:

- the complete profile set passes once from merged or pull-request code;
- the same complete profile set is repeated and major timing variation is
  explained;
- every hard correctness gate passes;
- timing guardrails pass or a reviewed catalog change explains the decision;
- retained reports pass the privacy scan; and
- the closing report states exact environment, version, workload, result,
  limitations, and recommendation.

## Planned repository structure

```text
tests/performance/
  payment_api.js
  profiles.js
  summary.js
tests/performance_harness/
  test_runner.py
  test_verifier.py
scripts/
  run_performance.py
  verify_performance.py
docs/quality/milestones/m8-performance-baseline/
  scenario-catalog.md
  quality-report.md
  example-summary.json
.github/workflows/
  performance.yml
```

The implementation may simplify names, but it should keep traffic generation,
orchestration, verification, and human evidence separate.

## Entry criteria

- Milestone 7 code and quality report are merged.
- The full Python and Chromium baseline is green.
- Proposed workload rates, duration, and timing guardrails are reviewed.
- The loopback-only target rule is approved.
- k6 version and installation method will be pinned in the implementation PR.
- Expected database counts are defined for each profile.
- Generated evidence fields and privacy scan patterns are agreed.

## Exit criteria

- Every planned harness and performance scenario has executed or is marked with
  a clear limitation.
- Hard correctness gates pass with exact financial counts.
- Authorization, retrieval, retry, and mixed timing results are recorded.
- No baseline profile drops an iteration.
- A controlled threshold failure proves that the workflow can block.
- Local commands work from a clean checkout.
- Pull-request, manual, and scheduled workflow paths are documented.
- JSON evidence is sanitized and retained for 14 days in CI.
- The README, quality index, traceability matrix, and final project summary match
  the delivered behavior.
- Genuine defects receive a numbered defect report and regression coverage.
- The closing report gives a clear proceed, proceed-with-limitations, or stop
  recommendation.

## Review questions

1. Are 5 authorizations per second and 10 retrievals per second suitable as the
   modest declared baseline for this local simulator?
2. Are the proposed p95 and p99 guardrails wide enough for runner variation but
   still useful for detecting a major regression?
3. Should the weekly scheduled profile run automatically, or should all longer
   runs remain manual to reduce CI usage?
4. Is a 20-request equivalent retry burst enough to demonstrate concurrency
   without turning this into a stress test?
5. Are authorization, retrieval, retry, and the mixed profile enough for the
   final milestone, while other lifecycle throughput remains an explicit limit?

## Decision record

| Decision | Review status | Reason |
|---|---|---|
| Use k6 OSS without a cloud account | Approved | The project remains local, repeatable, and free of external data transfer |
| Use arrival-rate executors for measured steady profiles | Approved | Offered traffic remains explicit when service latency changes |
| Keep correctness gates stricter than timing guardrails | Approved | Financial or response errors are not acceptable because timing looks good |
| Verify database effects outside k6 | Approved | VUs are isolated, and database counts are a stronger cross-layer oracle |
| Run only against loopback with no remote override | Approved | Prevents accidental traffic to an unapproved target |
| Use `handleSummary()` for sanitized JSON | Approved | It gives a small reviewed evidence format instead of every request sample |
| Run smoke on relevant pull requests and longer profiles manually or weekly | Approved | Pull requests stay fast while baseline evidence remains automated |
| Treat timing values as simulator guardrails, not production SLOs | Approved | One process and SQLite cannot represent distributed production capacity |
