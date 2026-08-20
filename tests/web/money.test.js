import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  formatMinorUnits,
  parseMinorUnits,
} from "../../src/payment_quality_lab/web/checkout/money.js";

describe("parseMinorUnits", () => {
  test("keeps a whole JPY amount in minor units", () => {
    assert.equal(parseMinorUnits("2500", "JPY"), 2500);
  });

  test("accepts the exact JPY maximum", () => {
    assert.equal(parseMinorUnits("999999999", "JPY"), 999_999_999);
  });

  test("rejects a decimal JPY amount", () => {
    assert.equal(parseMinorUnits("2500.0", "JPY"), null);
  });

  test("rejects zero JPY", () => {
    assert.equal(parseMinorUnits("0", "JPY"), null);
  });

  test("rejects a negative JPY amount", () => {
    assert.equal(parseMinorUnits("-1", "JPY"), null);
  });

  test("rejects surrounding whitespace", () => {
    assert.equal(parseMinorUnits(" 2500", "JPY"), null);
  });

  test("rejects a JPY amount above the API maximum", () => {
    assert.equal(parseMinorUnits("1000000000", "JPY"), null);
  });

  test("converts whole USD to cents", () => {
    assert.equal(parseMinorUnits("25", "USD"), 2500);
  });

  test("pads one USD decimal digit", () => {
    assert.equal(parseMinorUnits("25.5", "USD"), 2550);
  });

  test("keeps two USD decimal digits exactly", () => {
    assert.equal(parseMinorUnits("25.50", "USD"), 2550);
  });

  test("rejects more than two USD decimal digits", () => {
    assert.equal(parseMinorUnits("25.501", "USD"), null);
  });

  test("rejects a USD amount above the minor-unit maximum", () => {
    assert.equal(parseMinorUnits("10000000.00", "USD"), null);
  });

  test("rejects unsupported currencies", () => {
    assert.equal(parseMinorUnits("25", "EUR"), null);
  });

  test("rejects non-string input", () => {
    assert.equal(parseMinorUnits(25, "JPY"), null);
  });
});

describe("formatMinorUnits", () => {
  test("formats English JPY without decimals", () => {
    assert.equal(formatMinorUnits(2500, "JPY", "en"), "¥2,500");
  });

  test("formats English USD with exactly two decimals", () => {
    assert.equal(formatMinorUnits(2550, "USD", "en"), "$25.50");
  });

  test("formats Japanese JPY with the exact amount", () => {
    const formatted = formatMinorUnits(2500, "JPY", "ja");

    assert.match(formatted, /2,500/);
    assert.doesNotMatch(formatted, /\.00/);
  });
});
