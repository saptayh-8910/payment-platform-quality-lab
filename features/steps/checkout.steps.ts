import assert from "node:assert/strict";

import { Given, Then, When } from "@cucumber/cucumber";

import { CheckoutPage } from "../pages/checkout-page.ts";
import {
  CheckoutWorld,
  type Currency,
  type Language,
  type Outcome,
  type PaymentResponse,
} from "../support/world.ts";

function languageFor(name: string): Language {
  return name === "Japanese" ? "ja" : "en";
}

function checkout(world: CheckoutWorld): CheckoutPage {
  return new CheckoutPage(world.requirePage(), world.baseUrl);
}

Given(
  "the checkout is open in {word}",
  async function (this: CheckoutWorld, languageName: string) {
    await checkout(this).open(languageFor(languageName));
  },
);

Given(
  "the first payment response will be lost after commit",
  async function (this: CheckoutWorld) {
    let firstRequest = true;
    await this.requireContext().route("**/payments", async (route) => {
      if (route.request().method() === "POST" && firstRequest) {
        firstRequest = false;
        await route.continue({
          headers: {
            ...route.request().headers(),
            "X-Payment-Lab-Failure": "after_commit",
          },
        });
        return;
      }
      await route.continue();
    });
  },
);

When(
  "the customer submits reference {string} for {string} {word} with outcome {word}",
  async function (
    this: CheckoutWorld,
    reference: string,
    amount: string,
    currency: Currency,
    outcome: Outcome,
  ) {
    const page = checkout(this);
    await page.enterPayment(reference, amount, currency, outcome);
    await page.submit();
  },
);

When(
  "the customer enters reference {string} for {string} {word} with outcome {word}",
  async function (
    this: CheckoutWorld,
    reference: string,
    amount: string,
    currency: Currency,
    outcome: Outcome,
  ) {
    await checkout(this).enterPayment(reference, amount, currency, outcome);
  },
);

When("switches the checkout to Japanese", async function (this: CheckoutWorld) {
  await checkout(this).switchLanguage("ja");
});

When("the customer submits the entered payment", async function (this: CheckoutWorld) {
  await checkout(this).submit();
});

When(
  "the customer selects the {word} outcome without submitting",
  async function (this: CheckoutWorld, outcome: Outcome) {
    await checkout(this).selectOutcome(outcome);
  },
);

When(
  "the customer rapidly submits twice for reference {string} and JPY {string}",
  async function (this: CheckoutWorld, reference: string, amount: string) {
    const page = checkout(this);
    await page.enterPayment(reference, amount, "JPY", "Approve");
    await page.submitRapidlyTwice();
  },
);

When(
  "the customer completes reference {string} and JPY {string} using only the keyboard",
  async function (this: CheckoutWorld, reference: string, amount: string) {
    await checkout(this).completeWithKeyboard(reference, amount);
  },
);

When("the customer retries the uncertain payment", async function (this: CheckoutWorld) {
  const events = (await this.getJson("/webhooks/events")) as Array<{
    payment_id: string;
    payload: { payment: { merchant_reference: string } };
  }>;
  const event = events.find(
    (candidate) => candidate.payload.payment.merchant_reference === "注文-再試行-001",
  );
  assert.ok(event, "Committed webhook event should exist before retry");
  this.committedPaymentId = event.payment_id;
  await checkout(this).retry();
});

When("the customer refreshes before retry", async function (this: CheckoutWorld) {
  await checkout(this).refresh();
});

Then("the result says {string}", async function (this: CheckoutWorld, expected: string) {
  const page = checkout(this);
  await page.waitForResult();
  assert.equal(await page.resultTitle(), expected);
});

Then(
  "the result says {string} in Japanese",
  async function (this: CheckoutWorld, expected: string) {
    const page = checkout(this);
    await page.waitForResult();
    assert.equal(await page.documentLanguage(), "ja");
    assert.equal(await page.resultTitle(), expected);
  },
);

Then(
  "the result shows {string} and status {string}",
  async function (this: CheckoutWorld, amount: string, status: string) {
    const page = checkout(this);
    assert.equal(await page.resultAmount(), amount);
    assert.equal(await page.resultStatus(), status);
  },
);

Then(
  "the decline guidance says {string}",
  async function (this: CheckoutWorld, expected: string) {
    assert.equal(await checkout(this).resultGuidance(), expected);
  },
);

Then(
  "no internal decline code is displayed",
  async function (this: CheckoutWorld) {
    const page = checkout(this);
    const payment = (await this.getJson(
      `/payments/${await page.paymentId()}`,
    )) as PaymentResponse;
    assert.equal(payment.status, "DECLINED");
    assert.ok(payment.decline_reason);
    assert.equal((await page.resultGuidance()).includes(payment.decline_reason), false);
    assert.equal((await page.resultGuidance()).includes("tok_declined"), false);
  },
);

Then(
  "browser storage contains no submitted payment token",
  async function (this: CheckoutWorld) {
    const storage = await this.requirePage().evaluate(() => JSON.stringify(sessionStorage));
    assert.equal(storage.includes("tok_"), false);
  },
);

Then(
  "the entered reference {string} and amount {string} remain",
  async function (this: CheckoutWorld, reference: string, amount: string) {
    const page = checkout(this);
    assert.equal(await page.documentLanguage(), "ja");
    assert.equal(await page.value("merchant-reference"), reference);
    assert.equal(await page.value("amount"), amount);
  },
);

Then(
  "the result keeps reference {string} and amount {string}",
  async function (this: CheckoutWorld, reference: string, amount: string) {
    const page = checkout(this);
    assert.equal(await page.resultReference(), reference);
    assert.equal(await page.resultAmount(), amount);
  },
);

Then(
  "the order preview shows reference {string} and amount {string}",
  async function (this: CheckoutWorld, reference: string, amount: string) {
    const page = checkout(this);
    assert.equal(await page.summaryReference(), reference);
    assert.equal(await page.summaryAmount(), amount);
  },
);

Then(
  "the payment action says {string}",
  async function (this: CheckoutWorld, expected: string) {
    assert.equal(await checkout(this).paymentActionLabel(), expected);
  },
);

Then("the test-environment warning is visible", async function (this: CheckoutWorld) {
  assert.equal(await checkout(this).testEnvironmentIsVisible(), true);
});

Then(
  "the outcome selector belongs only to the simulator controls",
  async function (this: CheckoutWorld) {
    assert.equal(await checkout(this).outcomeBelongsOnlyToSimulator(), true);
  },
);

Then(
  "the checkout shows a synthetic method without credential fields",
  async function (this: CheckoutWorld) {
    assert.equal(await checkout(this).checkoutUsesSyntheticMethodWithoutCredentialFields(), true);
  },
);

Then(
  "the customer checkout does not reveal the planned outcome",
  async function (this: CheckoutWorld) {
    assert.equal(await checkout(this).checkoutRevealsOutcome(), false);
  },
);

Then(
  "the payment has {word} ledger entry and one webhook event",
  async function (this: CheckoutWorld, countWord: string) {
    const expectedCount = countWord === "one" ? 1 : 0;
    await assertFinancialEvidence(this, expectedCount);
  },
);

Then(
  "the payment has zero ledger entries and one webhook event",
  async function (this: CheckoutWorld) {
    await assertFinancialEvidence(this, 0);
  },
);

Then("the API stores 2550 minor units", async function (this: CheckoutWorld) {
  const page = checkout(this);
  const payment = (await this.getJson(`/payments/${await page.paymentId()}`)) as PaymentResponse;
  assert.equal(payment.amount, 2550);
  assert.equal(payment.currency, "USD");
});

Then(
  "the amount error says {string}",
  async function (this: CheckoutWorld, expected: string) {
    assert.equal(await checkout(this).errorText("amount"), expected);
  },
);

Then("keyboard focus moves to the error summary", async function (this: CheckoutWorld) {
  assert.equal(await checkout(this).hasErrorSummaryFocus(), true);
});

Then("the browser sent one payment request", function (this: CheckoutWorld) {
  assert.equal(this.paymentRequestCount, 1);
});

Then("the browser sent zero payment requests", function (this: CheckoutWorld) {
  assert.equal(this.paymentRequestCount, 0);
});

Then("the browser requested no external resources", function (this: CheckoutWorld) {
  assert.deepEqual(this.externalRequestUrls, []);
});

Then("the browser loaded no failed presentation resources", function (this: CheckoutWorld) {
  assert.deepEqual(this.failedPresentationResources, []);
});

When("the customer waits without taking action", async function (this: CheckoutWorld) {
  await this.requirePage().waitForTimeout(500);
});

Then("a Japanese retry action is available", async function (this: CheckoutWorld) {
  const page = checkout(this);
  assert.equal(await page.retryIsVisible(), true);
  assert.equal(await page.resultGuidance(), "同じ内容で再試行してください。新しい決済を作成する必要はありません。");
});

Then(
  "the uncertain Japanese result and retry action remain available",
  async function (this: CheckoutWorld) {
    const page = checkout(this);
    await page.waitForResult();
    assert.equal(await page.documentLanguage(), "ja");
    assert.equal(await page.resultTitle(), "結果を確認できません");
    assert.equal(await page.retryIsVisible(), true);
  },
);

Then(
  "the original payment survives refresh with one financial effect",
  async function (this: CheckoutWorld) {
    const page = checkout(this);
    await page.waitForResult();
    const paymentId = await page.paymentId();
    assert.equal(paymentId, this.committedPaymentId);
    assert.equal(this.observedIdempotencyKeys.length, 2);
    assert.equal(this.observedIdempotencyKeys[0], this.observedIdempotencyKeys[1]);

    await this.requirePage().reload();
    await page.waitForResult();
    assert.equal(await page.paymentId(), paymentId);
    assert.equal(this.paymentRequestCount, 2);
    await assertFinancialEvidence(this, 1);
  },
);

Then(
  "the page has semantic controls and no horizontal overflow",
  async function (this: CheckoutWorld) {
    const page = checkout(this);
    assert.equal(await page.semanticStructureIsPresent(), true);
    assert.equal(await page.pageHasHorizontalOverflow(), false);
  },
);

async function assertFinancialEvidence(world: CheckoutWorld, expectedLedgerEntries: number) {
  const paymentId = await checkout(world).paymentId();
  assert.match(paymentId, /^pay_/);
  const ledger = (await world.getJson(`/payments/${paymentId}/ledger`)) as unknown[];
  const events = (await world.getJson("/webhooks/events")) as Array<{ payment_id: string }>;
  assert.equal(ledger.length, expectedLedgerEntries);
  assert.equal(events.filter((event) => event.payment_id === paymentId).length, 1);
}
