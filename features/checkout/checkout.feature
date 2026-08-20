Feature: Multilingual test checkout
  The checkout must communicate exact synthetic payment outcomes in English and
  Japanese while preserving the platform's duplicate-payment protection.

  @critical @smoke
  Scenario: English JPY payment is authorized
    Given the checkout is open in English
    When the customer submits reference "order-browser-001" for "2500" JPY with outcome Approve
    Then the result says "Payment authorized"
    And the result shows "¥2,500" and status "Authorized"
    And the payment has one ledger entry and one webhook event

  @critical @localization
  Scenario: Japanese JPY payment preserves its reference
    Given the checkout is open in English
    When the customer enters reference "注文-東京-001" for "2500" JPY with outcome Approve
    And switches the checkout to Japanese
    Then the entered reference "注文-東京-001" and amount "2500" remain
    When the customer submits the entered payment
    Then the result says "決済が承認されました" in Japanese
    And the result keeps reference "注文-東京-001" and amount "￥2,500"

  @critical @currency
  Scenario: USD display amount is converted and shown exactly
    Given the checkout is open in English
    When the customer submits reference "order-usd-001" for "25.50" USD with outcome Approve
    Then the result says "Payment authorized"
    And the result shows "$25.50" and status "Authorized"
    And the API stores 2550 minor units

  @localization @negative
  Scenario: Japanese declined payment is explained clearly
    Given the checkout is open in Japanese
    When the customer submits reference "注文-拒否-001" for "2500" JPY with outcome Decline
    Then the result says "決済が拒否されました" in Japanese
    And the result shows "￥2,500" and status "拒否"
    And the payment has zero ledger entries and one webhook event

  @localization @accessibility @negative
  Scenario: Invalid amount gives localized keyboard guidance
    Given the checkout is open in Japanese
    When the customer submits reference "注文-入力-001" for "25.5" JPY with outcome Approve
    Then the amount error says "有効な金額を入力してください。"
    And keyboard focus moves to the error summary

  @critical @reliability
  Scenario: Repeated submission creates one payment effect
    Given the checkout is open in English
    When the customer rapidly submits twice for reference "order-repeat-001" and JPY "2500"
    Then the result says "Payment authorized"
    And the browser sent one payment request
    And the payment has one ledger entry and one webhook event

  @critical @reliability @localization
  Scenario: Japanese uncertain result is retried safely
    Given the checkout is open in Japanese
    And the first payment response will be lost after commit
    When the customer submits reference "注文-再試行-001" for "2500" JPY with outcome Approve
    Then the result says "結果を確認できません" in Japanese
    And a Japanese retry action is available
    When the customer retries the uncertain payment
    Then the original payment survives refresh with one financial effect

  @critical @mobile @accessibility @localization
  Scenario: Checkout completes by keyboard at the mobile viewport
    Given the checkout is open in Japanese
    When the customer completes reference "注文-モバイル-001" and JPY "2500" using only the keyboard
    Then the result says "決済が承認されました" in Japanese
    And the page has semantic controls and no horizontal overflow
