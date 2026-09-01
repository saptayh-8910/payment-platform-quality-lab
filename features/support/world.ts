import { World, setWorldConstructor, type IWorldOptions } from "@cucumber/cucumber";
import type { BrowserContext, Page } from "playwright";

export type Language = "en" | "ja";
export type Currency = "JPY" | "USD";
export type Outcome =
  | "Approve"
  | "Decline"
  | "InsufficientFunds"
  | "LimitExceeded"
  | "Expired"
  | "VerificationFailed"
  | "Invalid"
  | "Unknown";

export interface PaymentResponse {
  id: string;
  merchant_reference: string;
  amount: number;
  currency: Currency;
  status: "AUTHORIZED" | "DECLINED";
  decline_reason: string | null;
}

export class CheckoutWorld extends World {
  baseUrl = "";
  context?: BrowserContext;
  page?: Page;
  paymentRequestCount = 0;
  observedIdempotencyKeys: string[] = [];
  committedPaymentId?: string;

  constructor(options: IWorldOptions) {
    super(options);
  }

  requirePage(): Page {
    if (!this.page) {
      throw new Error("Browser page is not ready");
    }
    return this.page;
  }

  requireContext(): BrowserContext {
    if (!this.context) {
      throw new Error("Browser context is not ready");
    }
    return this.context;
  }

  async getJson(path: string): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}${path}`);
    if (!response.ok) {
      throw new Error(`GET ${path} returned ${response.status}`);
    }
    return response.json();
  }
}

setWorldConstructor(CheckoutWorld);
