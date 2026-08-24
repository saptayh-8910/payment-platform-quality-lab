import http from "k6/http";
import { check, fail } from "k6";
import exec from "k6/execution";
import { Counter, Gauge, Trend } from "k6/metrics";

import { optionsFor } from "./profiles.js";
import { summaryOutputs } from "./summary.js";

const PROFILE = __ENV.PROFILE;
const RUN_ID = __ENV.RUN_ID;
const SUMMARY_PATH = __ENV.SUMMARY_PATH || "k6-summary.json";
const BASE_URL = validateTarget(__ENV.BASE_URL);
const FORCE_THRESHOLD_FAILURE = __ENV.FORCE_THRESHOLD_FAILURE === "true";

const authorizationDuration = new Trend("authorization_duration", true);
const retrievalDuration = new Trend("retrieval_duration", true);
const replayDuration = new Trend("replay_duration", true);
const forcedGate = new Gauge("forced_gate");
const setupAuthorizations = new Counter("setup_authorizations");
const measuredAuthorizations = new Counter("measured_authorizations");
const warmupRetrievals = new Counter("warmup_retrievals");
const measuredRetrievals = new Counter("measured_retrievals");
const warmupReplays = new Counter("warmup_replays");
const measuredReplays = new Counter("measured_replays");

export const options = optionsFor(PROFILE, FORCE_THRESHOLD_FAILURE);

function validateTarget(rawTarget) {
  const match = /^http:\/\/(127\.0\.0\.1|localhost):([0-9]{1,5})$/.exec(
    rawTarget || "",
  );
  if (!match) {
    throw new Error("BASE_URL must be an explicit loopback HTTP origin");
  }
  const port = Number(match[2]);
  if (port < 1 || port > 65535) {
    throw new Error("BASE_URL must contain a valid loopback port");
  }
  return rawTarget;
}

function currencyFor(index) {
  return index % 2 === 0 ? "JPY" : "USD";
}

function amountFor(currency) {
  return currency === "JPY" ? 2500 : 1099;
}

function paymentInput(phase, index, outcome = "approved") {
  const currency = currencyFor(index);
  return {
    body: {
      merchant_reference: `perf-${RUN_ID}-${PROFILE}-${phase}-${index}`,
      amount: amountFor(currency),
      currency,
      payment_method_token:
        outcome === "approved" ? "tok_approved" : "tok_declined",
    },
    key: `perf-${RUN_ID}-${PROFILE}-${phase}-${index}-key`,
    currency,
    outcome,
  };
}

function parseBody(response) {
  try {
    return response.json();
  } catch (_error) {
    return {};
  }
}

function authorize(input, phase, measuredTrend = null) {
  const response = http.post(`${BASE_URL}/payments`, JSON.stringify(input.body), {
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": input.key,
    },
    tags: {
      operation: "authorize",
      profile: PROFILE,
      currency: input.currency,
      outcome: input.outcome,
      phase,
    },
  });
  const body = parseBody(response);
  check(response, {
    "authorization returns created": (result) => result.status === 201,
    "authorization returns expected reference": () =>
      body.merchant_reference === input.body.merchant_reference,
    "authorization returns expected money": () =>
      body.amount === input.body.amount && body.currency === input.body.currency,
    "authorization returns expected outcome": () =>
      body.status === (input.outcome === "approved" ? "AUTHORIZED" : "DECLINED"),
  });
  if (measuredTrend) {
    measuredTrend.add(response.timings.duration);
  }
  if (phase === "setup" || phase === "warmup") {
    setupAuthorizations.add(1);
  } else {
    measuredAuthorizations.add(1);
  }
  return body;
}

function retrieve(paymentId, expectedReference, phase, measuredTrend = null) {
  const response = http.get(`${BASE_URL}/payments/${paymentId}`, {
    tags: { operation: "retrieve", profile: PROFILE, phase },
  });
  const body = parseBody(response);
  check(response, {
    "retrieval returns success": (result) => result.status === 200,
    "retrieval returns expected payment": () =>
      body.id === paymentId && body.merchant_reference === expectedReference,
  });
  if (measuredTrend) {
    measuredTrend.add(response.timings.duration);
  }
  if (phase === "warmup") {
    warmupRetrievals.add(1);
  } else if (phase === "measured") {
    measuredRetrievals.add(1);
  }
  return body;
}

function createPool(size) {
  const pool = [];
  for (let index = 0; index < size; index += 1) {
    const input = paymentInput("setup", index);
    const payment = authorize(input, "setup");
    pool.push({ id: payment.id, reference: input.body.merchant_reference });
  }
  return pool;
}

export function setup() {
  if (PROFILE === "smoke") {
    return {};
  }
  if (PROFILE === "authorization") {
    for (let index = 0; index < 5; index += 1) {
      authorize(paymentInput("warmup", index), "warmup");
    }
    return {};
  }
  if (PROFILE === "retrieval" || PROFILE === "mixed") {
    const pool = createPool(20);
    for (let index = 0; index < 5; index += 1) {
      retrieve(pool[index].id, pool[index].reference, "warmup");
    }
    return { pool };
  }
  if (PROFILE === "idempotent-burst") {
    const input = paymentInput("setup", 0);
    const payment = authorize(input, "setup");
    const warmup = replay(input, payment.id, "warmup", null);
    if (warmup.id !== payment.id) {
      fail("idempotent warm-up returned another payment");
    }
    return { input, paymentId: payment.id };
  }
  fail(`Unknown PROFILE: ${PROFILE}`);
}

export function smoke() {
  const index = exec.scenario.iterationInTest;
  const input = paymentInput("load", index, index === 4 ? "declined" : "approved");
  const payment = authorize(input, "measured");
  if (index < 4) {
    retrieve(payment.id, input.body.merchant_reference, "measured");
  }
  forcedGate.add(0);
}

export function authorization() {
  const index = exec.scenario.iterationInTest;
  authorize(paymentInput("load", index), "measured", authorizationDuration);
  forcedGate.add(0);
}

export function retrieval(data) {
  const index = exec.scenario.iterationInTest % data.pool.length;
  const payment = data.pool[index];
  retrieve(payment.id, payment.reference, "measured", retrievalDuration);
  forcedGate.add(0);
}

function replay(input, paymentId, phase, measuredTrend = replayDuration) {
  const response = http.post(`${BASE_URL}/payments`, JSON.stringify(input.body), {
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": input.key,
    },
    tags: { operation: "idempotent_replay", profile: PROFILE, phase },
  });
  const body = parseBody(response);
  check(response, {
    "replay returns success": (result) => result.status === 200,
    "replay is identified": (result) => result.headers["Idempotent-Replayed"] === "true",
    "replay returns original payment": () => body.id === paymentId,
    "replay returns original money": () =>
      body.amount === input.body.amount && body.currency === input.body.currency,
  });
  if (measuredTrend) {
    measuredTrend.add(response.timings.duration);
  }
  if (phase === "warmup") {
    warmupReplays.add(1);
  } else if (phase === "measured") {
    measuredReplays.add(1);
  }
  return body;
}

export function idempotentReplay(data) {
  replay(data.input, data.paymentId, "measured");
  forcedGate.add(0);
}

export function mixedAuthorization() {
  const index = exec.scenario.iterationInTest;
  authorize(paymentInput("load", index), "measured", authorizationDuration);
  forcedGate.add(0);
}

export function mixedRetrieval(data) {
  const index = exec.scenario.iterationInTest % data.pool.length;
  const payment = data.pool[index];
  retrieve(payment.id, payment.reference, "measured", retrievalDuration);
  forcedGate.add(0);
}

export function handleSummary(data) {
  return summaryOutputs(data, RUN_ID, PROFILE, SUMMARY_PATH);
}
