import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const stylesheet = readFileSync(
  new URL("../../src/payment_quality_lab/web/checkout/styles.css", import.meta.url),
  "utf8",
);

function colorToken(name) {
  const match = stylesheet.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert.ok(match, `Expected ${name} in checkout design tokens`);
  return match[1];
}

function relativeLuminance(hexColor) {
  const channels = hexColor
    .slice(1)
    .match(/.{2}/g)
    .map((channel) => Number.parseInt(channel, 16) / 255)
    .map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(first, second) {
  const firstLuminance = relativeLuminance(first);
  const secondLuminance = relativeLuminance(second);
  return (
    (Math.max(firstLuminance, secondLuminance) + 0.05) /
    (Math.min(firstLuminance, secondLuminance) + 0.05)
  );
}

describe("checkout design-token contrast", () => {
  const surface = colorToken("--color-surface");

  for (const name of [
    "--color-ink",
    "--color-muted",
    "--color-primary",
    "--color-success",
    "--color-danger",
    "--color-warning",
  ]) {
    it(`${name} meets 4.5:1 against the checkout surface`, () => {
      assert.ok(
        contrastRatio(colorToken(name), surface) >= 4.5,
        `${name} must meet the normal-text target`,
      );
    });
  }

  for (const name of ["--color-focus", "--color-control-border"]) {
    it(`${name} meets 3:1 against the checkout surface`, () => {
      assert.ok(
        contrastRatio(colorToken(name), surface) >= 3,
        `${name} must meet the non-text target`,
      );
    });
  }
});
