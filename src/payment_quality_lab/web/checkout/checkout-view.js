import { formatMinorUnits, parseMinorUnits } from "./money.js";

export const UI_STATES = Object.freeze({
  EDITING: "editing",
  RESTORING: "restoring",
  PROCESSING: "processing",
  FINAL: "final",
  UNCERTAIN: "uncertain",
  ERROR: "error",
});

export const UI_EVENTS = Object.freeze({
  START_RESTORE: "start-restore",
  RESTORE_EMPTY: "restore-empty",
  START_SUBMISSION: "start-submission",
  PAYMENT_RESOLVED: "payment-resolved",
  RESULT_UNCERTAIN: "result-uncertain",
  SHOW_ERROR: "show-error",
  RESET: "reset",
});

const allowedTransitions = Object.freeze({
  [UI_STATES.EDITING]: Object.freeze({
    [UI_EVENTS.START_RESTORE]: UI_STATES.RESTORING,
    [UI_EVENTS.START_SUBMISSION]: UI_STATES.PROCESSING,
    [UI_EVENTS.SHOW_ERROR]: UI_STATES.ERROR,
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
  [UI_STATES.RESTORING]: Object.freeze({
    [UI_EVENTS.RESTORE_EMPTY]: UI_STATES.EDITING,
    [UI_EVENTS.PAYMENT_RESOLVED]: UI_STATES.FINAL,
    [UI_EVENTS.RESULT_UNCERTAIN]: UI_STATES.UNCERTAIN,
    [UI_EVENTS.SHOW_ERROR]: UI_STATES.ERROR,
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
  [UI_STATES.PROCESSING]: Object.freeze({
    [UI_EVENTS.PAYMENT_RESOLVED]: UI_STATES.FINAL,
    [UI_EVENTS.RESULT_UNCERTAIN]: UI_STATES.UNCERTAIN,
    [UI_EVENTS.SHOW_ERROR]: UI_STATES.ERROR,
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
  [UI_STATES.FINAL]: Object.freeze({
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
  [UI_STATES.UNCERTAIN]: Object.freeze({
    [UI_EVENTS.START_SUBMISSION]: UI_STATES.PROCESSING,
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
  [UI_STATES.ERROR]: Object.freeze({
    [UI_EVENTS.RESET]: UI_STATES.EDITING,
  }),
});

export function transitionUiState(currentState, event) {
  const nextState = allowedTransitions[currentState]?.[event];
  if (!nextState) {
    throw new Error(`Invalid checkout UI transition: ${currentState} -> ${event}`);
  }
  return nextState;
}

export function deriveOrderPreview({ merchantReference, displayAmount, currency, language }) {
  const amount = parseMinorUnits(displayAmount, currency);
  return Object.freeze({
    merchantReference: merchantReference || null,
    amount,
    formattedAmount: amount === null ? null : formatMinorUnits(amount, currency, language),
  });
}

export function paymentActionLabel({ defaultLabel, amountTemplate, formattedAmount }) {
  if (!formattedAmount) {
    return defaultLabel;
  }
  return amountTemplate.replace("{amount}", formattedAmount);
}
