export const asyncCopy = {
  en: {
    delayedOutcome: "Await later confirmation", paymentReference: "Payment reference",
    deadline: "Confirmation deadline (Japan time)", refresh: "Check payment status",
    stale: "We could not check the latest status. The result below may be out of date. Try checking again.",
    AWAITING_PAYMENT: ["Waiting for payment confirmation", "Keep this reference. This test payment is waiting for confirmation. Do not make a real payment."],
    EXPIRED: ["Payment request expired", "This request has expired. If you already paid, contact support with your reference before trying again. This simulator does not process real payments."],
    CAPTURED: ["Payment confirmed", "This test payment has been confirmed. No real money was processed."],
    CANCELLED: ["Payment request cancelled", "This request was cancelled. If you already paid, contact support with your reference."],
    PARTIALLY_REFUNDED: ["Payment partially refunded", "Part of this test payment was refunded. No real money was processed."],
    REFUNDED: ["Payment refunded", "This test payment was refunded. No real money was processed."],
  },
  ja: {
    delayedOutcome: "後からの確認を待つ", paymentReference: "決済参照番号",
    deadline: "確認期限（日本時間）", refresh: "支払い状況を確認",
    stale: "最新の状況を確認できませんでした。以下の結果は最新ではない可能性があります。もう一度確認してください。",
    AWAITING_PAYMENT: ["お支払いの確認待ちです", "この参照番号を控えてください。このテスト決済は確認待ちです。実際の支払いはしないでください。"],
    EXPIRED: ["支払いリクエストの期限が切れました", "このリクエストは期限切れです。すでに支払いをした場合は、再度支払う前に参照番号を添えてサポートにお問い合わせください。このシミュレーターでは実際の決済は行いません。"],
    CAPTURED: ["お支払いを確認しました", "このテスト決済の確認が完了しました。実際のお金は処理されていません。"],
    CANCELLED: ["支払いリクエストはキャンセルされました", "このリクエストはキャンセルされました。すでに支払いをした場合は、参照番号を添えてサポートにお問い合わせください。"],
    PARTIALLY_REFUNDED: ["一部返金済みです", "このテスト決済の一部を返金しました。実際のお金は処理されていません。"],
    REFUNDED: ["返金済みです", "このテスト決済を返金しました。実際のお金は処理されていません。"],
  },
};

export function formatDeadline(value, language) {
  return new Intl.DateTimeFormat(language === "ja" ? "ja-JP" : "en-GB", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(new Date(value));
}
