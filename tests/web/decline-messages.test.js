import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  declineGuidance,
  guidanceForDecline,
} from "../../src/payment_quality_lab/web/checkout/decline-messages.js";

const reasons = [
  "insufficient_funds",
  "limit_exceeded",
  "expired_payment_method",
  "verification_failed",
  "invalid_payment_method",
  "unknown",
];

describe("decline guidance", () => {
  for (const language of ["en", "ja"]) {
    for (const reason of reasons) {
      it(`maps ${reason} to customer guidance in ${language}`, () => {
        const guidance = guidanceForDecline(reason, language);

        assert.equal(guidance, declineGuidance[language][reason]);
        assert.ok(guidance.length > 0);
        assert.notEqual(guidance, reason);
        assert.equal(guidance.includes(reason), false);
      });
    }
  }

  it("uses safe generic guidance for a future reason and unsupported language", () => {
    assert.equal(
      guidanceForDecline("future_reason", "en"),
      declineGuidance.en.unknown,
    );
    assert.equal(
      guidanceForDecline("future_reason", "unsupported"),
      declineGuidance.en.unknown,
    );
  });
});
