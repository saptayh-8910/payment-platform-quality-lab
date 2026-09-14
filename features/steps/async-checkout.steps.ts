import assert from "node:assert/strict";
import { Given, When, Then } from "@cucumber/cucumber";
import { CheckoutWorld } from "../support/world.ts";

Given("an awaiting test payment is displayed in {string}", async function(this: CheckoutWorld, lang: string) {
  const page = this.requirePage();
  await page.goto(`${this.baseUrl}/checkout?lang=${lang}`);
  await page.locator("#merchant-reference").fill("async-browser-order");
  await page.locator("#amount").fill("2500");
  await page.locator("#outcome").selectOption("tok_awaiting_confirmation");
  const received = page.waitForResponse(r => r.url().endsWith("/payments") && r.request().method() === "POST");
  await page.locator("button[type=submit]").click();
  const payment = await (await received).json();
  this.committedPaymentId = payment.id;
  await page.locator("#delayed-details").waitFor();
  assert.equal(await page.locator("#delayed-details dd").first().textContent(), payment.payment_reference);
  const title = await page.locator("#result-title").textContent();
  await page.clock.setFixedTime(new Date("2030-01-01T00:00:00Z"));
  assert.equal(await page.locator("#result-title").textContent(), title);
  assert.match(await page.locator("#delayed-details").innerText(), /ref_/);
  assert.equal(this.paymentRequestCount, 1);
});

When("the backend resolves the test payment as {string}", async function(this: CheckoutWorld, outcome: string) {
  const response = await fetch(`${this.baseUrl}/test/payments/${this.committedPaymentId}/${outcome}`, {method: "POST"});
  assert.equal(response.status, 200);
});

Then("manual refresh shows {string} without another payment", async function(this: CheckoutWorld, title: string) {
  const page = this.requirePage();
  await page.locator("#refresh-payment").click();
  await page.waitForFunction(expected => document.querySelector("#result-title")?.textContent === expected, title);
  assert.equal(this.paymentRequestCount, 1);
  assert.equal(await page.locator("#refresh-payment").isEnabled(), true);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.doesNotMatch(await page.locator("#result-panel").innerText(), /AWAITING_PAYMENT|EXPIRED|CAPTURED|already_resolved/);
});

Then("delayed details survive language switch and reload", async function(this: CheckoutWorld) {
  const page = this.requirePage();
  const reference = await page.locator("#delayed-details dd").first().textContent();
  let requests = 0;
  const listen = () => { requests += 1; };
  page.on("request", listen);
  const current = await page.locator("html").getAttribute("lang");
  await page.locator(`[data-language='${current === "ja" ? "en" : "ja"}']`).click();
  assert.equal(await page.locator("#delayed-details dd").first().textContent(), reference);
  assert.equal(requests, 0);
  page.off("request", listen);
  await page.reload();
  await page.locator("#delayed-details").waitFor();
  assert.equal(await page.locator("#delayed-details dd").first().textContent(), reference);
  assert.equal(await page.locator("#outcome").inputValue(), "tok_awaiting_confirmation");
  assert.equal(this.paymentRequestCount, 1);
  await page.locator("#new-payment").click();
  assert.equal(await page.locator("#result-panel").isVisible(), false);
});

Then("a failed refresh preserves the reference and offers another check", async function(this: CheckoutWorld) {
  const page = this.requirePage();
  const reference = await page.locator("#delayed-details").innerText();
  await page.route("**/payments/*", route => route.abort());
  await page.locator("#refresh-payment").click();
  await page.locator("#refresh-warning").waitFor();
  assert.match(await page.locator("#refresh-warning").innerText(), /out of date/);
  assert.equal(await page.locator("#delayed-details").innerText(), reference);
  await page.unroute("**/payments/*");
  await page.locator("#refresh-payment").click();
  await page.waitForFunction(() => (document.querySelector("#refresh-warning") as HTMLElement).hidden);
  assert.equal(this.paymentRequestCount, 1);
});
