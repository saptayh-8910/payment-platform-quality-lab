import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  deriveOrderPreview,
  paymentActionLabel,
  transitionUiState,
  UI_EVENTS,
  UI_STATES,
} from "../../src/payment_quality_lab/web/checkout/checkout-view.js";

describe("checkout UI state", () => {
  it("moves an approved submission through processing to a final result", () => {
    const processing = transitionUiState(UI_STATES.EDITING, UI_EVENTS.START_SUBMISSION);
    assert.equal(processing, UI_STATES.PROCESSING);
    assert.equal(
      transitionUiState(processing, UI_EVENTS.PAYMENT_RESOLVED),
      UI_STATES.FINAL,
    );
  });

  it("allows an uncertain request to retry through the same processing state", () => {
    const uncertain = transitionUiState(UI_STATES.PROCESSING, UI_EVENTS.RESULT_UNCERTAIN);
    assert.equal(uncertain, UI_STATES.UNCERTAIN);
    assert.equal(
      transitionUiState(uncertain, UI_EVENTS.START_SUBMISSION),
      UI_STATES.PROCESSING,
    );
  });

  it("restores either a final, uncertain, or empty browser state", () => {
    assert.equal(
      transitionUiState(UI_STATES.RESTORING, UI_EVENTS.PAYMENT_RESOLVED),
      UI_STATES.FINAL,
    );
    assert.equal(
      transitionUiState(UI_STATES.RESTORING, UI_EVENTS.RESULT_UNCERTAIN),
      UI_STATES.UNCERTAIN,
    );
    assert.equal(
      transitionUiState(UI_STATES.RESTORING, UI_EVENTS.RESTORE_EMPTY),
      UI_STATES.EDITING,
    );
  });

  it("rejects a transition that would silently resubmit a final result", () => {
    assert.throws(
      () => transitionUiState(UI_STATES.FINAL, UI_EVENTS.START_SUBMISSION),
      /Invalid checkout UI transition/,
    );
  });
});

describe("derived checkout view", () => {
  it("derives an exact Japanese JPY summary without creating a payment", () => {
    assert.deepEqual(
      deriveOrderPreview({
        merchantReference: "注文-東京-001",
        displayAmount: "2500",
        currency: "JPY",
        language: "ja",
      }),
      {
        merchantReference: "注文-東京-001",
        amount: 2500,
        formattedAmount: "￥2,500",
      },
    );
  });

  it("does not format an invalid amount", () => {
    assert.deepEqual(
      deriveOrderPreview({
        merchantReference: "order-invalid",
        displayAmount: "25.5",
        currency: "JPY",
        language: "en",
      }),
      {
        merchantReference: "order-invalid",
        amount: null,
        formattedAmount: null,
      },
    );
  });

  it("puts a valid amount into English and Japanese action labels", () => {
    assert.equal(
      paymentActionLabel({
        defaultLabel: "Pay",
        amountTemplate: "Pay {amount}",
        formattedAmount: "¥2,500",
      }),
      "Pay ¥2,500",
    );
    assert.equal(
      paymentActionLabel({
        defaultLabel: "支払う",
        amountTemplate: "{amount}を支払う",
        formattedAmount: "￥2,500",
      }),
      "￥2,500を支払う",
    );
  });
});
