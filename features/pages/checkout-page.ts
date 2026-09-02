import type { Page } from "playwright";

import type { Currency, Language, Outcome } from "../support/world.ts";

const tokenByOutcome: Record<Outcome, string> = {
  Approve: "tok_approved",
  Decline: "tok_declined_unknown",
  InsufficientFunds: "tok_declined_insufficient_funds",
  LimitExceeded: "tok_declined_limit_exceeded",
  Expired: "tok_declined_expired",
  VerificationFailed: "tok_declined_verification",
  Invalid: "tok_declined_invalid",
  Unknown: "tok_declined_unknown",
};

export class CheckoutPage {
  private readonly page: Page;
  private readonly baseUrl: string;

  constructor(page: Page, baseUrl: string) {
    this.page = page;
    this.baseUrl = baseUrl;
  }

  async open(language: Language): Promise<void> {
    await this.page.goto(`${this.baseUrl}/checkout?lang=${language}`);
  }

  async enterPayment(
    reference: string,
    displayAmount: string,
    currency: Currency,
    outcome: Outcome,
  ): Promise<void> {
    await this.page.locator("#merchant-reference").fill(reference);
    await this.page.locator("#amount").fill(displayAmount);
    await this.page.locator("#currency").selectOption(currency);
    await this.page.locator("#outcome").selectOption(tokenByOutcome[outcome]);
  }

  async submit(): Promise<void> {
    await this.page.locator("#submit-payment").click();
  }

  async selectOutcome(outcome: Outcome): Promise<void> {
    await this.page.locator("#outcome").selectOption(tokenByOutcome[outcome]);
  }

  async submitRapidlyTwice(): Promise<void> {
    await this.page.locator("#submit-payment").evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  }

  async completeWithKeyboard(reference: string, amount: string): Promise<void> {
    await this.page.locator("#merchant-reference").focus();
    await this.page.keyboard.type(reference);
    await this.page.keyboard.press("Tab");
    await this.page.keyboard.type(amount);
    await this.page.keyboard.press("Tab");
    await this.page.keyboard.press("Tab");
    await this.page.keyboard.press("Tab");
    await this.page.keyboard.press("Enter");
  }

  async switchLanguage(language: Language): Promise<void> {
    await this.page.locator(`[data-language="${language}"]`).click();
  }

  async retry(): Promise<void> {
    await this.page.locator("#retry-payment").click();
  }

  async refresh(): Promise<void> {
    await this.page.reload();
  }

  async waitForResult(): Promise<void> {
    await this.page.locator("#result-panel").waitFor({ state: "visible" });
  }

  async resultTitle(): Promise<string> {
    return (await this.page.locator("#result-title").textContent()) ?? "";
  }

  async resultGuidance(): Promise<string> {
    return (await this.page.locator("#result-guidance").textContent()) ?? "";
  }

  async resultAmount(): Promise<string> {
    return (await this.page.locator("#result-amount").textContent()) ?? "";
  }

  async resultReference(): Promise<string> {
    return (await this.page.locator("#result-reference").textContent()) ?? "";
  }

  async resultStatus(): Promise<string> {
    return (await this.page.locator("#result-payment-status").textContent()) ?? "";
  }

  async summaryReference(): Promise<string> {
    return (await this.page.locator("#summary-reference").textContent()) ?? "";
  }

  async summaryAmount(): Promise<string> {
    return (await this.page.locator("#summary-amount").textContent()) ?? "";
  }

  async paymentActionLabel(): Promise<string> {
    return (await this.page.locator("#submit-payment").textContent())?.trim() ?? "";
  }

  async testEnvironmentIsVisible(): Promise<boolean> {
    return this.page.locator(".environment-banner").isVisible();
  }

  async outcomeBelongsOnlyToSimulator(): Promise<boolean> {
    return this.page.evaluate(() => {
      const outcome = document.querySelector("#outcome");
      return Boolean(
        outcome?.closest("[data-region='simulator']") &&
          !outcome?.closest("[data-region='checkout']"),
      );
    });
  }

  async checkoutUsesSyntheticMethodWithoutCredentialFields(): Promise<boolean> {
    return this.page.evaluate(() => {
      const checkout = document.querySelector("[data-region='checkout']");
      const syntheticMethod = checkout?.querySelector("[data-i18n='syntheticMethod']");
      const credentialField = checkout?.querySelector("input, select, textarea");
      return Boolean(syntheticMethod && !credentialField);
    });
  }

  async checkoutRevealsOutcome(): Promise<boolean> {
    const checkoutText = await this.page.locator("[data-region='checkout']").innerText();
    return /insufficient|declin|残高不足|拒否/i.test(checkoutText);
  }

  async paymentId(): Promise<string> {
    return (await this.page.locator("#result-payment-id").textContent()) ?? "";
  }

  async errorText(field: "amount" | "merchant-reference"): Promise<string> {
    return (await this.page.locator(`#${field}-error`).textContent()) ?? "";
  }

  async hasErrorSummaryFocus(): Promise<boolean> {
    return this.page.locator("#error-summary").evaluate((element) => element === document.activeElement);
  }

  async value(field: "amount" | "merchant-reference"): Promise<string> {
    return this.page.locator(`#${field}`).inputValue();
  }

  async documentLanguage(): Promise<string> {
    return this.page.locator("html").getAttribute("lang").then((value) => value ?? "");
  }

  async retryIsVisible(): Promise<boolean> {
    return this.page.locator("#retry-payment").isVisible();
  }

  async pageHasHorizontalOverflow(): Promise<boolean> {
    return this.page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  }

  async semanticStructureIsPresent(): Promise<boolean> {
    return this.page.evaluate(() => {
      const labelledControls = [...document.querySelectorAll("input, select")].every((control) =>
        Boolean(control.id && document.querySelector(`label[for="${control.id}"]`)),
      );
      return Boolean(
        document.querySelector("main") &&
          document.querySelectorAll("h1").length === 1 &&
          document.querySelector("[data-region='simulator']") &&
          document.querySelector("[data-region='checkout']") &&
          document.querySelector("[role='status'][aria-live]") &&
          labelledControls,
      );
    });
  }
}
