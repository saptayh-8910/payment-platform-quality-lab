import assert from "node:assert/strict";
import test from "node:test";
import { asyncCopy, formatDeadline } from "../../src/payment_quality_lab/web/checkout/async-messages.js";

for (const language of ["en", "ja"]) {
  test(`delayed copy covers backend states in ${language}`, () => {
    for (const status of ["AWAITING_PAYMENT", "EXPIRED", "CAPTURED", "CANCELLED", "PARTIALLY_REFUNDED", "REFUNDED"]) {
      assert.equal(asyncCopy[language][status].length, 2);
      assert.ok(asyncCopy[language][status].every(text => text.length > 0 && !text.includes(status)));
    }
  });
  test(`deadline uses Japan timezone in ${language}`, () => {
    const result = formatDeadline("2026-09-14T16:00:00Z", language);
    assert.match(result, /15/);
    assert.match(result, /01:00:00/);
  });
}
