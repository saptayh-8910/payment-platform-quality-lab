export const declineGuidance = Object.freeze({
  en: Object.freeze({
    insufficient_funds:
      "Available funds may be insufficient. Check the balance or try another payment method.",
    limit_exceeded:
      "The amount may exceed a permitted limit. Try a permitted amount or another payment method.",
    expired_payment_method:
      "This payment method may have expired. Update it or try another payment method.",
    verification_failed:
      "Some payment information could not be verified. Check the information and try again.",
    invalid_payment_method:
      "This payment method could not be used. Check it or try another payment method.",
    unknown:
      "The payment could not be completed. Try again later or use another payment method.",
  }),
  ja: Object.freeze({
    insufficient_funds:
      "利用可能残高が不足している可能性があります。残高を確認するか、別の決済方法をお試しください。",
    limit_exceeded:
      "利用限度額を超えている可能性があります。利用可能な金額に変更するか、別の決済方法をお試しください。",
    expired_payment_method:
      "この決済方法の有効期限が切れている可能性があります。情報を更新するか、別の決済方法をお試しください。",
    verification_failed:
      "一部の決済情報を確認できませんでした。入力内容を確認して、もう一度お試しください。",
    invalid_payment_method:
      "この決済方法は利用できませんでした。内容を確認するか、別の決済方法をお試しください。",
    unknown:
      "決済を完了できませんでした。時間をおいて再試行するか、別の決済方法をお試しください。",
  }),
});

export function guidanceForDecline(reason, language) {
  const selectedLanguage = language === "ja" ? "ja" : "en";
  return declineGuidance[selectedLanguage][reason] ?? declineGuidance[selectedLanguage].unknown;
}
