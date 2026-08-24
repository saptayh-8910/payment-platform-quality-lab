const RETAINED_METRICS = [
  "checks",
  "http_reqs",
  "http_req_failed",
  "http_req_duration",
  "iterations",
  "dropped_iterations",
  "vus",
  "vus_max",
  "authorization_duration",
  "retrieval_duration",
  "replay_duration",
  "forced_gate",
  "setup_authorizations",
  "measured_authorizations",
  "warmup_retrievals",
  "measured_retrievals",
  "warmup_replays",
  "measured_replays",
];

const RETAINED_VALUES = [
  "rate",
  "count",
  "avg",
  "min",
  "med",
  "max",
  "p(90)",
  "p(95)",
  "p(99)",
  "value",
];

function sanitizedMetric(metric) {
  const values = {};
  for (const name of RETAINED_VALUES) {
    if (metric.values && metric.values[name] !== undefined) {
      values[name] = metric.values[name];
    }
  }
  const thresholds = {};
  for (const [name, result] of Object.entries(metric.thresholds || {})) {
    thresholds[name] = { passed: result.ok === true };
  }
  return { values, thresholds };
}

export function buildSummary(data, runId, profile) {
  const metrics = {};
  let passed = true;
  for (const name of RETAINED_METRICS) {
    const metric = data.metrics[name];
    if (!metric) {
      continue;
    }
    metrics[name] = sanitizedMetric(metric);
    for (const result of Object.values(metric.thresholds || {})) {
      if (result.ok !== true) {
        passed = false;
      }
    }
  }
  return {
    schema_version: 1,
    run_id: runId,
    profile,
    target: "isolated-loopback",
    tool: { name: "k6", version: "v2.0.0" },
    passed,
    metrics,
  };
}

export function summaryOutputs(data, runId, profile, summaryPath) {
  const summary = buildSummary(data, runId, profile);
  const decision = summary.passed ? "PASS" : "FAIL";
  return {
    stdout: `\nPerformance measurements: ${decision}; profile=${profile}; run_id=${runId}\n`,
    [summaryPath]: `${JSON.stringify(summary, null, 2)}\n`,
  };
}
