Feature: Multilingual test checkout
  The checkout must communicate exact synthetic payment outcomes in English and
  Japanese while preserving the platform's duplicate-payment protection.

  @critical @smoke
  Scenario: English JPY payment is authorized
    Given the checkout is open in English
    When the customer enters reference "order-browser-001" for "2500" JPY with outcome Approve
    Then the order preview shows reference "order-browser-001" and amount "¥2,500"
    And the payment action says "Pay ¥2,500"
    When the customer submits the entered payment
    Then the result says "Payment authorized"
    And the result shows "¥2,500" and status "Authorized"
    And the payment has one ledger entry and one webhook event

  @critical @localization
  Scenario: Japanese JPY payment preserves its reference
    Given the checkout is open in English
    When the customer enters reference "注文-東京-001" for "2500" JPY with outcome Approve
    And switches the checkout to Japanese
    Then the entered reference "注文-東京-001" and amount "2500" remain
    And the order preview shows reference "注文-東京-001" and amount "￥2,500"
    And the payment action says "￥2,500を支払う"
    When the customer submits the entered payment
    Then the result says "決済が承認されました" in Japanese
    And the result keeps reference "注文-東京-001" and amount "￥2,500"

  @critical @currency
  Scenario: USD display amount is converted and shown exactly
    Given the checkout is open in English
    When the customer enters reference "order-usd-001" for "25.50" USD with outcome Approve
    Then the order preview shows reference "order-usd-001" and amount "$25.50"
    And the payment action says "Pay $25.50"
    When the customer submits the entered payment
    Then the result says "Payment authorized"
    And the result shows "$25.50" and status "Authorized"
    And the API stores 2550 minor units

  @critical @localization @negative @detailed-decline
  Scenario Outline: Insufficient-funds guidance follows the selected language
    Given the checkout is open in <language>
    When the customer submits reference "decline-guidance-001" for "2500" JPY with outcome InsufficientFunds
    Then the result says "<title>"
    And the result shows "<amount>" and status "<status>"
    And the decline guidance says "<guidance>"
    And no internal decline code is displayed
    And browser storage contains no submitted payment token
    And the payment has zero ledger entries and one webhook event

    Examples: English desktop
      | language | title                  | amount | status   | guidance |
      | English  | Payment declined       | ¥2,500 | Declined | Available funds may be insufficient. Check the balance or try another payment method. |

    @mobile
    Examples: Japanese mobile
      | language | title                  | amount | status   | guidance |
      | Japanese | 決済が拒否されました   | ￥2,500 | 拒否     | 利用可能残高が不足している可能性があります。残高を確認するか、別の決済方法をお試しください。 |

  @critical @trust-boundary
  Scenario: Simulator controls stay outside the customer checkout
    Given the checkout is open in English
    Then the test-environment warning is visible
    And the outcome selector belongs only to the simulator controls
    And the checkout shows a synthetic method without credential fields
    When the customer selects the InsufficientFunds outcome without submitting
    Then the customer checkout does not reveal the planned outcome
    And the browser sent zero payment requests
    And the browser requested no external resources

  @negative @reliability
  Scenario: Declined result does not resubmit without customer action
    Given the checkout is open in English
    When the customer submits reference "decline-no-resubmit-001" for "2500" JPY with outcome Unknown
    Then the result says "Payment declined"
    And the browser sent one payment request
    When the customer waits without taking action
    Then the browser sent one payment request

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
    When the customer refreshes before retry
    Then the uncertain Japanese result and retry action remain available
    When the customer retries the uncertain payment
    Then the original payment survives refresh with one financial effect

  @critical @mobile @accessibility @localization
  Scenario: Checkout completes by keyboard at the mobile viewport
    Given the checkout is open in Japanese
    When the customer completes reference "注文-モバイル-001" and JPY "2500" using only the keyboard
    Then the result says "決済が承認されました" in Japanese
    And the page has semantic controls and no horizontal overflow
