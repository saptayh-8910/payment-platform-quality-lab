import { formatMinorUnits, parseMinorUnits } from "/checkout/assets/money.js";
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

const copy = {
  en: {
    pageTitle: "Payment test",
    brand: "Payment Quality Lab",
    languageNavigation: "Language",
    eyebrow: "Privacy-safe simulator",
    introduction: "Test payment behavior with synthetic outcomes. Do not enter real payment data.",
    formTitle: "Test details",
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
    submit: "Run test payment",
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
    formTitle: "テスト内容",
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
    submit: "テスト決済を実行",
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
  formPanel: document.querySelector("#checkout-panel"),
  reference: document.querySelector("#merchant-reference"),
  amount: document.querySelector("#amount"),
  currency: document.querySelector("#currency"),
  outcome: document.querySelector("#outcome"),
  submit: document.querySelector("#submit-payment"),
  submitLabel: document.querySelector("#submit-payment [data-i18n]"),
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

  if (currentPayment) {
    renderPayment(currentPayment);
  } else if (!elements.resultPanel.hidden) {
    if (elements.resultPanel.dataset.result === "uncertain") {
      renderUncertain();
    } else if (elements.resultPanel.dataset.result === "error") {
      renderError(currentErrorKey);
    }
  }
  if (!elements.errorSummary.hidden) {
    validateForm();
  }
  if (elements.submit.disabled) {
    elements.submitLabel.textContent = copy[language].processing;
  }
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

function validateForm() {
  clearValidation();
  let valid = true;

  if (!elements.reference.value) {
    showFieldError(elements.reference, copy[language].required);
    valid = false;
  } else if ([...elements.reference.value].length > 64) {
    showFieldError(elements.reference, copy[language].referenceTooLong);
    valid = false;
  }

  const amount = parseMinorUnits(elements.amount.value, elements.currency.value);
  if (!elements.amount.value) {
    showFieldError(elements.amount, copy[language].required);
    valid = false;
  } else if (amount === null) {
    showFieldError(elements.amount, copy[language].invalidAmount);
    valid = false;
  }

  if (!valid) {
    elements.errorSummary.hidden = false;
    elements.errorSummary.focus();
    return null;
  }
  return amount;
}

function setProcessing(processing) {
  elements.submit.disabled = processing;
  elements.submitLabel.textContent = processing ? copy[language].processing : copy[language].submit;
  elements.progress.hidden = !processing;
  elements.liveStatus.textContent = processing ? copy[language].processing : "";
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

  setProcessing(true);
  elements.resultPanel.hidden = true;
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
      renderPayment(body);
    } else if (response.status === 504 && body.code === "payment_timeout") {
      renderUncertain();
    } else {
      clearActiveSubmission();
      renderError("generalError");
    }
  } catch {
    renderUncertain();
  } finally {
    setProcessing(false);
  }
}

function showResultShell(kind) {
  elements.formPanel.hidden = true;
  elements.resultPanel.hidden = false;
  elements.resultPanel.dataset.result = kind;
  elements.resultStatus.textContent = kind === "success" ? "✓" : kind === "decline" ? "×" : "?";
  elements.resultPanel.focus({ preventScroll: true });
}

function renderPayment(payment) {
  const authorized = payment.status === "AUTHORIZED";
  showResultShell(authorized ? "success" : "decline");
  elements.resultTitle.textContent = authorized ? copy[language].authorized : copy[language].declined;
  elements.resultGuidance.textContent = authorized
    ? copy[language].authorizedGuidance
    : guidanceForDecline(payment.decline_reason, language);
  elements.paymentDetails.hidden = false;
  elements.paymentId.textContent = payment.id;
  elements.resultReference.textContent = payment.merchant_reference;
  elements.resultAmount.textContent = formatMinorUnits(payment.amount, payment.currency, language);
  elements.paymentStatus.textContent = authorized
    ? copy[language].authorizedStatus
    : copy[language].declinedStatus;
  elements.retry.hidden = true;
  elements.newPayment.hidden = false;
  elements.liveStatus.textContent = elements.resultTitle.textContent;
}

function renderUncertain() {
  currentPayment = null;
  showResultShell("uncertain");
  elements.resultTitle.textContent = copy[language].uncertain;
  elements.resultGuidance.textContent = copy[language].uncertainGuidance;
  elements.paymentDetails.hidden = true;
  elements.retry.hidden = false;
  elements.newPayment.hidden = true;
  elements.liveStatus.textContent = copy[language].uncertain;
}

function renderError(messageKey) {
  currentPayment = null;
  currentErrorKey = messageKey;
  showResultShell("error");
  elements.resultTitle.textContent = copy[language].generalError;
  elements.resultGuidance.textContent = copy[language][messageKey];
  elements.paymentDetails.hidden = true;
  elements.retry.hidden = true;
  elements.newPayment.hidden = false;
  elements.liveStatus.textContent = copy[language][messageKey];
}

function resetCheckout() {
  currentPayment = null;
  clearActiveSubmission();
  sessionStorage.removeItem(lastPaymentStorageName);
  elements.form.reset();
  clearValidation();
  elements.resultPanel.hidden = true;
  elements.formPanel.hidden = false;
  elements.reference.focus();
}

async function restorePayment() {
  const paymentId = sessionStorage.getItem(lastPaymentStorageName);
  if (paymentId) {
    try {
      const response = await fetch(`/payments/${encodeURIComponent(paymentId)}`);
      if (!response.ok) {
        sessionStorage.removeItem(lastPaymentStorageName);
        renderError("missingResult");
        return;
      }
      currentPayment = await response.json();
      renderPayment(currentPayment);
    } catch {
      renderError("generalError");
    }
    return;
  }

  const key = sessionStorage.getItem(activeKeyStorageName);
  const submission = readActiveSubmission();
  if (!key && !submission) {
    return;
  }
  if (!key || key.length < 8 || key.length > 128 || !submission) {
    clearActiveSubmission();
    return;
  }

  elements.reference.value = submission.merchantReference;
  elements.amount.value =
    submission.currency === "JPY"
      ? String(submission.amount)
      : `${Math.floor(submission.amount / 100)}.${String(submission.amount % 100).padStart(2, "0")}`;
  elements.currency.value = submission.currency;
  elements.outcome.value = tokenByStoredOutcome[submission.outcome];
  renderUncertain();
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!elements.submit.disabled) {
    void submitPayment();
  }
});
elements.retry.addEventListener("click", () => void submitPayment());
elements.newPayment.addEventListener("click", resetCheckout);
for (const button of document.querySelectorAll("[data-language]")) {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
}

setLanguage(language);
void restorePayment();
