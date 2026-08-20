const MAX_MINOR_UNITS = 999_999_999;

/**
 * Convert a customer-facing amount string to integer minor units.
 * The function intentionally avoids Number(value) and floating-point arithmetic.
 */
export function parseMinorUnits(value, currency) {
  if (typeof value !== "string") {
    return null;
  }

  if (currency === "JPY") {
    if (!/^[0-9]+$/.test(value)) {
      return null;
    }

    return boundedInteger(value);
  }

  if (currency === "USD") {
    const match = /^([0-9]+)(?:\.([0-9]{1,2}))?$/.exec(value);
    if (!match) {
      return null;
    }

    const fractional = (match[2] ?? "").padEnd(2, "0");
    return boundedInteger(`${match[1]}${fractional}`);
  }

  return null;
}

function boundedInteger(digits) {
  const normalized = digits.replace(/^0+(?=[0-9])/, "");
  const amount = BigInt(normalized);
  if (amount <= 0n || amount > BigInt(MAX_MINOR_UNITS)) {
    return null;
  }
  return Number(amount);
}

export function formatMinorUnits(amount, currency, language) {
  const locale = language === "ja" ? "ja-JP" : "en-US";
  const value = currency === "USD" ? amount / 100 : amount;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: currency === "USD" ? 2 : 0,
    maximumFractionDigits: currency === "USD" ? 2 : 0,
  }).format(value);
}
