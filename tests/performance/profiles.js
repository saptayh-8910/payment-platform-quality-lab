const COMMON_THRESHOLDS = {
  checks: ["rate==1"],
  http_req_failed: ["rate==0"],
  dropped_iterations: ["count==0"],
};

const EXACT_COUNT_THRESHOLDS = {
  smoke: {
    measured_authorizations: ["count==5"],
    measured_retrievals: ["count==4"],
  },
  authorization: {
    setup_authorizations: ["count==5"],
    measured_authorizations: ["count==150"],
  },
  retrieval: {
    setup_authorizations: ["count==20"],
    warmup_retrievals: ["count==5"],
    measured_retrievals: ["count==300"],
  },
  "idempotent-burst": {
    setup_authorizations: ["count==1"],
    warmup_replays: ["count==1"],
    measured_replays: ["count==20"],
  },
  mixed: {
    setup_authorizations: ["count==20"],
    warmup_retrievals: ["count==5"],
    measured_authorizations: ["count==120"],
    measured_retrievals: ["count==480"],
  },
};

const ARRIVAL_VUS = {
  preAllocatedVUs: 10,
  maxVUs: 40,
};

const COMMON_OPTIONS = {
  discardResponseBodies: false,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
};

// k6 v2.0.0 can schedule at a scenario's closing boundary. These values stay
// within the catalog's rounded 30- and 60-second windows while preserving the
// exact reviewed iteration totals enforced by the custom counter thresholds.
const THIRTY_SECOND_WINDOW = "29.999s";
const SIXTY_SECOND_WINDOW = "59.9s";

export function optionsFor(profile, forceThresholdFailure) {
  const exactCounts = EXACT_COUNT_THRESHOLDS[profile];
  if (!exactCounts) {
    throw new Error(`Unknown PROFILE: ${profile}`);
  }
  const thresholds = { ...COMMON_THRESHOLDS, ...exactCounts };
  if (forceThresholdFailure) {
    thresholds.forced_gate = ["value==1"];
  }

  if (profile === "smoke") {
    return {
      ...COMMON_OPTIONS,
      scenarios: {
        smoke: {
          executor: "shared-iterations",
          exec: "smoke",
          vus: 1,
          iterations: 5,
          maxDuration: "30s",
        },
      },
      thresholds,
    };
  }

  if (profile === "authorization") {
    thresholds.authorization_duration = ["p(95)<500", "p(99)<1000"];
    return {
      ...COMMON_OPTIONS,
      scenarios: {
        authorization: {
          executor: "constant-arrival-rate",
          exec: "authorization",
          rate: 5,
          timeUnit: "1s",
          duration: THIRTY_SECOND_WINDOW,
          ...ARRIVAL_VUS,
        },
      },
      thresholds,
    };
  }

  if (profile === "retrieval") {
    thresholds.retrieval_duration = ["p(95)<250", "p(99)<500"];
    return {
      ...COMMON_OPTIONS,
      scenarios: {
        retrieval: {
          executor: "constant-arrival-rate",
          exec: "retrieval",
          rate: 10,
          timeUnit: "1s",
          duration: THIRTY_SECOND_WINDOW,
          ...ARRIVAL_VUS,
        },
      },
      thresholds,
    };
  }

  if (profile === "idempotent-burst") {
    thresholds.replay_duration = ["p(95)<750", "p(99)<1500"];
    return {
      ...COMMON_OPTIONS,
      scenarios: {
        idempotent_burst: {
          executor: "shared-iterations",
          exec: "idempotentReplay",
          vus: 20,
          iterations: 20,
          maxDuration: "30s",
        },
      },
      thresholds,
    };
  }

  if (profile === "mixed") {
    thresholds.authorization_duration = ["p(95)<500", "p(99)<1000"];
    thresholds.retrieval_duration = ["p(95)<250", "p(99)<500"];
    return {
      ...COMMON_OPTIONS,
      scenarios: {
        mixed_authorization: {
          executor: "constant-arrival-rate",
          exec: "mixedAuthorization",
          rate: 2,
          timeUnit: "1s",
          duration: SIXTY_SECOND_WINDOW,
          ...ARRIVAL_VUS,
        },
        mixed_retrieval: {
          executor: "constant-arrival-rate",
          exec: "mixedRetrieval",
          rate: 8,
          timeUnit: "1s",
          duration: SIXTY_SECOND_WINDOW,
          ...ARRIVAL_VUS,
        },
      },
      thresholds,
    };
  }

  throw new Error(`Unknown PROFILE: ${profile}`);
}
