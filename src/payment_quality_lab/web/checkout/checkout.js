import {
  deriveOrderPreview,
  paymentActionLabel,
  transitionUiState,
  UI_EVENTS,
  UI_STATES,
} from "/checkout/assets/checkout-view.js";
import { guidanceForDecline } from "/checkout/assets/decline-messages.js";

const storedOutcomeByToken = Object.freeze({
  tok_approved: "approve",
  tok_declined_insufficient_funds: "decline-insufficient-funds",
  tok_declined_limit_exceeded: "decline-limit-exceeded",
  tok_declined_expired: "decline-expired",
  tok_declined_verification: "decline-verification",
  tok_declined_invalid: "decline-invalid",
  tok_declined_unknown: "decline-unknown",
});

const tokenByStoredOutcome = Object.freeze(
  Object.fromEntries(Object.entries(storedOutcomeByToken).map(([token, outcome]) => [outcome, token])),
);

const tokenByDeclineReason = Object.freeze({
  insufficient_funds: "tok_declined_insufficient_funds",
  limit_exceeded: "tok_declined_limit_exceeded",
  expired_payment_method: "tok_declined_expired",
  verification_failed: "tok_declined_verification",
  invalid_payment_method: "tok_declined_invalid",
  unknown: "tok_declined_unknown",
});

const copy = {
  en: {
    pageTitle: "Payment test",
    brand: "Payment Quality Lab",
    languageNavigation: "Language",
    eyebrow: "Privacy-safe simulator",
    introduction: "Test payment behavior with synthetic outcomes. Do not enter real payment data.",
    environmentLabel: "Test environment",
    environmentWarning: "Do not enter real payment information.",
    formTitle: "Simulator controls",
    simulatorExplanation:
      "These settings control the test scenario. They are not customer payment choices.",
    errorTitle: "Check the following fields",
    merchantReference: "Order reference",
    merchantReferenceHelp: "Use a synthetic reference only.",
    amount: "Amount",
    amountHelp: "Enter a whole JPY amount or up to two decimal places for USD.",
    currency: "Currency",
    outcome: "Test outcome",
    approve: "Approve",
    declineInsufficientFunds: "Decline — insufficient funds",
    declineLimitExceeded: "Decline — limit exceeded",
    declineExpired: "Decline — expired payment method",
    declineVerification: "Decline — verification failed",
    declineInvalid: "Decline — invalid payment method",
    declineUnknown: "Decline — other reason",
    outcomeHelp: "This controls the simulator. It is not a payment method.",
    checkoutTitle: "Test checkout",
    testOnly: "Test only",
    orderSummary: "Order summary",
    total: "Total",
    paymentMethod: "Payment method",
    syntheticMethod: "Synthetic payment method",
    pay: "Pay",
    payWithAmount: "Pay {amount}",
    processing: "Processing…",
    resultLabel: "Result",
    paymentId: "Payment ID",
    status: "Status",
    authorized: "Payment authorized",
    declined: "Payment declined",
    authorizedStatus: "Authorized",
    declinedStatus: "Declined",
    authorizedGuidance: "The synthetic authorization completed successfully.",
    uncertain: "The result is uncertain",
    uncertainGuidance: "Retry with the same details. A new payment request is not needed.",
    retry: "Retry",
    newCheckout: "New test payment",
    required: "This field is required.",
    invalidAmount: "Enter a valid amount.",
    referenceTooLong: "Use 64 characters or fewer.",
    generalError: "We could not complete the request. Please try again.",
    missingResult: "The saved payment result is no longer available.",
    footer: "Synthetic simulator only. No real payments or customer data are processed.",
  },
  ja: {
    pageTitle: "決済テスト",
    brand: "Payment Quality Lab",
    languageNavigation: "言語",
    eyebrow: "個人情報を使用しないシミュレーター",
    introduction: "テスト用の結果で決済の動作を確認します。実際の決済情報は入力しないでください。",
    environmentLabel: "テスト環境",
    environmentWarning: "実際の決済情報は入力しないでください。",
    formTitle: "シミュレーター設定",
    simulatorExplanation:
      "これらの設定はテストシナリオを制御します。実際の決済方法ではありません。",
    errorTitle: "入力内容を確認してください",
    merchantReference: "注文番号",
    merchantReferenceHelp: "テスト用の注文番号のみを使用してください。",
    amount: "金額",
    amountHelp: "JPYは整数、USDは小数点以下2桁まで入力できます。",
    currency: "通貨",
    outcome: "テスト結果",
    approve: "承認",
    declineInsufficientFunds: "拒否 — 残高不足",
    declineLimitExceeded: "拒否 — 利用限度額超過",
    declineExpired: "拒否 — 有効期限切れ",
    declineVerification: "拒否 — 情報確認失敗",
    declineInvalid: "拒否 — 利用できない決済方法",
    declineUnknown: "拒否 — その他の理由",
    outcomeHelp: "シミュレーターの結果を選びます。実際の決済方法ではありません。",
    checkoutTitle: "テスト決済",
    testOnly: "テスト専用",
    orderSummary: "ご注文内容",
    total: "合計",
    paymentMethod: "決済方法",
    syntheticMethod: "テスト用決済方法",
    pay: "支払う",
    payWithAmount: "{amount}を支払う",
    processing: "処理中です…",
    resultLabel: "結果",
    paymentId: "決済ID",
    status: "ステータス",
    authorized: "決済が承認されました",
    declined: "決済が拒否されました",
    authorizedStatus: "承認済み",
    declinedStatus: "拒否",
    authorizedGuidance: "テスト用の承認が完了しました。",
    uncertain: "結果を確認できません",
    uncertainGuidance: "同じ内容で再試行してください。新しい決済を作成する必要はありません。",
    retry: "再試行",
    newCheckout: "新しいテスト決済",
    required: "この項目は必須です。",
    invalidAmount: "有効な金額を入力してください。",
    referenceTooLong: "64文字以内で入力してください。",
    generalError: "処理を完了できませんでした。もう一度お試しください。",
    missingResult: "保存された決済結果を確認できません。",
    footer: "テスト用シミュレーターです。実際の決済情報や個人情報は処理しません。",
  },
};

const elements = {
  form: document.querySelector("#checkout-form"),
  checkoutCard: document.querySelector("[data-region='checkout']"),
  disclosure: document.querySelector("#simulator-disclosure"),
  fields: document.querySelector("#simulator-fields"),
  reference: document.querySelector("#merchant-reference"),
  amount: document.querySelector("#amount"),
  currency: document.querySelector("#currency"),
  outcome: document.querySelector("#outcome"),
  summaryReference: document.querySelector("#summary-reference"),
  summaryAmount: document.querySelector("#summary-amount"),
  summaryCurrency: document.querySelector("#summary-currency"),
  actionPanel: document.querySelector("#payment-action-panel"),
  submit: document.querySelector("#submit-payment"),
  submitLabel: document.querySelector("[data-submit-label]"),
  progress: document.querySelector("[data-progress]"),
  errorSummary: document.querySelector("#error-summary"),
  errorList: document.querySelector("#error-list"),
  resultPanel: document.querySelector("#result-panel"),
  resultTitle: document.querySelector("#result-title"),
  resultGuidance: document.querySelector("#result-guidance"),
  resultStatus: document.querySelector("#result-status"),
  paymentDetails: document.querySelector("#payment-details"),
  paymentId: document.querySelector("#result-payment-id"),
  resultReference: document.querySelector("#result-reference"),
  resultAmount: document.querySelector("#result-amount"),
  paymentStatus: document.querySelector("#result-payment-status"),
  retry: document.querySelector("#retry-payment"),
  newPayment: document.querySelector("#new-payment"),
  liveStatus: document.querySelector("#live-status"),
};

let language = readLanguage();
let uiState = UI_STATES.EDITING;
let currentPayment = null;
let currentErrorKey = "generalError";

const activeKeyStorageName = "paymentLab.activeIdempotencyKey";
const activeSubmissionStorageName = "paymentLab.activeSubmission";
const lastPaymentStorageName = "paymentLab.lastPaymentId";

function readLanguage() {
  const requested = new URLSearchParams(window.location.search).get("lang");
  return requested === "ja" ? "ja" : "en";
}

function setLanguage(nextLanguage) {
  language = nextLanguage === "ja" ? "ja" : "en";
  document.documentElement.lang = language;
  document.title = copy[language].pageTitle;

  const url = new URL(window.location.href);
  url.searchParams.set("lang", language);
  window.history.replaceState({}, "", url);

  for (const element of document.querySelectorAll("[data-i18n]")) {
    const key = element.dataset.i18n;
    if (copy[language][key]) {
      element.textContent = copy[language][key];
    }
  }
  for (const element of document.querySelectorAll("[data-i18n-aria-label]")) {
    element.setAttribute("aria-label", copy[language][element.dataset.i18nAriaLabel]);
  }
  for (const button of document.querySelectorAll("[data-language]")) {
    const selected = button.dataset.language === language;
    button.setAttribute("aria-pressed", String(selected));
  }

  if (!elements.errorSummary.hidden) {
    validateForm({ focusError: false });
  }
  renderUi();
}

function clearValidation() {
  elements.errorSummary.hidden = true;
  elements.errorList.replaceChildren();
  for (const field of [elements.reference, elements.amount]) {
    field.removeAttribute("aria-invalid");
    const error = document.querySelector(`#${field.id}-error`);
    error.hidden = true;
    error.textContent = "";
  }
}

function showFieldError(field, message) {
  field.setAttribute("aria-invalid", "true");
  const error = document.querySelector(`#${field.id}-error`);
  error.textContent = message;
  error.hidden = false;

  const item = document.createElement("li");
  const link = document.createElement("a");
  link.href = `#${field.id}`;
  link.textContent = message;
  item.append(link);
  elements.errorList.append(item);
}

function validateForm({ focusError = true } = {}) {
  clearValidation();
  let valid = true;

  if (!elements.reference.value) {
    showFieldError(elements.reference, copy[language].required);
    valid = false;
  } else if ([...elements.reference.value].length > 64) {
    showFieldError(elements.reference, copy[language].referenceTooLong);
    valid = false;
  }

  const preview = currentOrderPreview();
  if (!elements.amount.value) {
    showFieldError(elements.amount, copy[language].required);
    valid = false;
  } else if (preview.amount === null) {
    showFieldError(elements.amount, copy[language].invalidAmount);
    valid = false;
  }

  if (!valid) {
    elements.errorSummary.hidden = false;
    if (focusError) {
      elements.errorSummary.focus();
    }
    return null;
  }
  return preview.amount;
}

function currentOrderPreview() {
  return deriveOrderPreview({
    merchantReference: elements.reference.value,
    displayAmount: elements.amount.value,
    currency: elements.currency.value,
    language,
  });
}

function renderOrderPreview() {
  const preview = currentOrderPreview();
  elements.summaryReference.textContent = preview.merchantReference || "—";
  elements.summaryReference.dataset.empty = String(!preview.merchantReference);
  elements.summaryAmount.textContent = preview.formattedAmount || "—";
  elements.summaryCurrency.textContent = elements.currency.value;
  elements.submitLabel.textContent =
    uiState === UI_STATES.PROCESSING || uiState === UI_STATES.RESTORING
      ? copy[language].processing
      : paymentActionLabel({
          defaultLabel: copy[language].pay,
          amountTemplate: copy[language].payWithAmount,
          formattedAmount: preview.formattedAmount,
        });
}

function renderUi({ focusResult = false } = {}) {
  const busy = uiState === UI_STATES.PROCESSING || uiState === UI_STATES.RESTORING;
  const showsResult = [UI_STATES.FINAL, UI_STATES.UNCERTAIN, UI_STATES.ERROR].includes(uiState);

  elements.fields.disabled = busy || showsResult;
  elements.submit.disabled = busy;
  elements.progress.hidden = !busy;
  elements.actionPanel.hidden = showsResult;
  elements.resultPanel.hidden = !showsResult;
  elements.checkoutCard.setAttribute("aria-busy", String(busy));
  renderOrderPreview();

  if (uiState === UI_STATES.FINAL) {
    renderFinalResult();
  } else if (uiState === UI_STATES.UNCERTAIN) {
    renderUncertainResult();
  } else if (uiState === UI_STATES.ERROR) {
    renderErrorResult();
  } else {
    elements.liveStatus.textContent = busy ? copy[language].processing : "";
  }

  if (focusResult && showsResult) {
    if (window.matchMedia("(max-width: 50rem)").matches) {
      elements.disclosure.open = false;
    }
    elements.resultPanel.focus({ preventScroll: true });
  }
}

function moveUi(event, options) {
  uiState = transitionUiState(uiState, event);
  renderUi(options);
}

function activeIdempotencyKey() {
  let key = sessionStorage.getItem(activeKeyStorageName);
  if (!key) {
    key = `checkout-${crypto.randomUUID()}`;
    sessionStorage.setItem(activeKeyStorageName, key);
  }
  return key;
}

function activeSubmission(amount) {
  return {
    merchantReference: elements.reference.value,
    amount,
    currency: elements.currency.value,
    outcome: storedOutcomeByToken[elements.outcome.value],
  };
}

function storeActiveSubmission(submission) {
  sessionStorage.setItem(activeSubmissionStorageName, JSON.stringify(submission));
}

function clearActiveSubmission() {
  sessionStorage.removeItem(activeKeyStorageName);
  sessionStorage.removeItem(activeSubmissionStorageName);
}

function readActiveSubmission() {
  const stored = sessionStorage.getItem(activeSubmissionStorageName);
  if (!stored) {
    return null;
  }

  try {
    const submission = JSON.parse(stored);
    if (
      typeof submission !== "object" ||
      submission === null ||
      typeof submission.merchantReference !== "string" ||
      submission.merchantReference.length === 0 ||
      [...submission.merchantReference].length > 64 ||
      !Number.isInteger(submission.amount) ||
      submission.amount <= 0 ||
      submission.amount > 999_999_999 ||
      !["JPY", "USD"].includes(submission.currency) ||
      !Object.hasOwn(tokenByStoredOutcome, submission.outcome)
    ) {
      return null;
    }
    return submission;
  } catch {
    return null;
  }
}

async function submitPayment() {
  const amount = validateForm();
  if (amount === null) {
    return;
  }

  moveUi(UI_EVENTS.START_SUBMISSION);
  const key = activeIdempotencyKey();
  storeActiveSubmission(activeSubmission(amount));

  try {
    const response = await fetch("/payments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
      },
      body: JSON.stringify({
        merchant_reference: elements.reference.value,
        amount,
        currency: elements.currency.value,
        payment_method_token: elements.outcome.value,
      }),
    });

    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      clearActiveSubmission();
      sessionStorage.setItem(lastPaymentStorageName, body.id);
      currentPayment = body;
      moveUi(UI_EVENTS.PAYMENT_RESOLVED, { focusResult: true });
    } else if (response.status === 504 && body.code === "payment_timeout") {
      currentPayment = null;
      moveUi(UI_EVENTS.RESULT_UNCERTAIN, { focusResult: true });
    } else {
      clearActiveSubmission();
      currentPayment = null;
      currentErrorKey = "generalError";
      moveUi(UI_EVENTS.SHOW_ERROR, { focusResult: true });
    }
  } catch {
    currentPayment = null;
    moveUi(UI_EVENTS.RESULT_UNCERTAIN, { focusResult: true });
  }
}

function renderFinalResult() {
  const authorized = currentPayment.status === "AUTHORIZED";
  const kind = authorized ? "success" : "decline";
  elements.resultPanel.dataset.result = kind;
  elements.resultStatus.textContent = authorized ? "✓" : "×";
  elements.resultTitle.textContent = authorized ? copy[language].authorized : copy[language].declined;
  elements.resultGuidance.textContent = authorized
    ? copy[language].authorizedGuidance
    : guidanceForDecline(currentPayment.decline_reason, language);
  elements.paymentDetails.hidden = false;
  elements.paymentId.textContent = currentPayment.id;
  elements.resultReference.textContent = currentPayment.merchant_reference;
  elements.resultAmount.textContent = currentOrderPreview().formattedAmount;
  elements.paymentStatus.textContent = authorized
    ? copy[language].authorizedStatus
    : copy[language].declinedStatus;
  elements.retry.hidden = true;
  elements.newPayment.hidden = false;
  elements.liveStatus.textContent = elements.resultTitle.textContent;
}

function renderUncertainResult() {
  elements.resultPanel.dataset.result = "uncertain";
  elements.resultStatus.textContent = "?";
  elements.resultTitle.textContent = copy[language].uncertain;
  elements.resultGuidance.textContent = copy[language].uncertainGuidance;
  elements.paymentDetails.hidden = true;
  elements.retry.hidden = false;
  elements.newPayment.hidden = true;
  elements.liveStatus.textContent = copy[language].uncertain;
}

function renderErrorResult() {
  elements.resultPanel.dataset.result = "error";
  elements.resultStatus.textContent = "!";
  elements.resultTitle.textContent = copy[language].generalError;
  elements.resultGuidance.textContent = copy[language][currentErrorKey];
  elements.paymentDetails.hidden = true;
  elements.retry.hidden = true;
  elements.newPayment.hidden = false;
  elements.liveStatus.textContent = copy[language][currentErrorKey];
}

function resetCheckout() {
  currentPayment = null;
  currentErrorKey = "generalError";
  clearActiveSubmission();
  sessionStorage.removeItem(lastPaymentStorageName);
  elements.form.reset();
  elements.disclosure.open = true;
  clearValidation();
  moveUi(UI_EVENTS.RESET);
  elements.reference.focus();
}

function displayAmountFromMinorUnits(amount, currency) {
  return currency === "JPY"
    ? String(amount)
    : `${Math.floor(amount / 100)}.${String(amount % 100).padStart(2, "0")}`;
}

function populateControlsFromPayment(payment) {
  elements.reference.value = payment.merchant_reference;
  elements.amount.value = displayAmountFromMinorUnits(payment.amount, payment.currency);
  elements.currency.value = payment.currency;
  elements.outcome.value =
    payment.status === "AUTHORIZED"
      ? "tok_approved"
      : (tokenByDeclineReason[payment.decline_reason] ?? "tok_declined_unknown");
}

async function restorePayment() {
  moveUi(UI_EVENTS.START_RESTORE);
  const paymentId = sessionStorage.getItem(lastPaymentStorageName);
  if (paymentId) {
    try {
      const response = await fetch(`/payments/${encodeURIComponent(paymentId)}`);
      if (!response.ok) {
        sessionStorage.removeItem(lastPaymentStorageName);
        currentErrorKey = "missingResult";
        moveUi(UI_EVENTS.SHOW_ERROR);
        return;
      }
      currentPayment = await response.json();
      populateControlsFromPayment(currentPayment);
      moveUi(UI_EVENTS.PAYMENT_RESOLVED);
    } catch {
      currentErrorKey = "generalError";
      moveUi(UI_EVENTS.SHOW_ERROR);
    }
    return;
  }

  const key = sessionStorage.getItem(activeKeyStorageName);
  const submission = readActiveSubmission();
  if (!key && !submission) {
    moveUi(UI_EVENTS.RESTORE_EMPTY);
    return;
  }
  if (!key || key.length < 8 || key.length > 128 || !submission) {
    clearActiveSubmission();
    moveUi(UI_EVENTS.RESTORE_EMPTY);
    return;
  }

  elements.reference.value = submission.merchantReference;
  elements.amount.value = displayAmountFromMinorUnits(submission.amount, submission.currency);
  elements.currency.value = submission.currency;
  elements.outcome.value = tokenByStoredOutcome[submission.outcome];
  currentPayment = null;
  moveUi(UI_EVENTS.RESULT_UNCERTAIN);
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!elements.submit.disabled) {
    void submitPayment();
  }
});
elements.retry.addEventListener("click", () => void submitPayment());
elements.newPayment.addEventListener("click", resetCheckout);
for (const field of [elements.reference, elements.amount]) {
  field.addEventListener("input", renderUi);
}
elements.currency.addEventListener("change", renderUi);
for (const button of document.querySelectorAll("[data-language]")) {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
}

setLanguage(language);
void restorePayment();
