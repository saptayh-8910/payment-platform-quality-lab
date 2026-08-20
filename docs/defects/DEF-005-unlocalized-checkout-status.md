# DEF-005: Japanese checkout displayed an English API status

## Summary

The Japanese payment result translated its heading and guidance but displayed
the raw API status `AUTHORIZED`. This mixed English technical content into a
customer-facing Japanese result.

## Detection

| Field | Evidence |
|---|---|
| Milestone | 6: English and Japanese checkout |
| Found by | Manual review of the 390 by 844 Japanese result |
| Affected requirement | M6 `LOC-05`: every customer-facing result message uses the selected language |
| Severity | Medium |
| Status | Resolved before release |

## Reproduction

1. Open `/checkout?lang=ja` at the mobile viewport.
2. Enter a synthetic Japanese reference and JPY amount.
3. Select the approval outcome and submit.
4. Inspect the status row in the completed result.

## Expected result

The Japanese result should use a clear Japanese status such as `承認済み`.

## Observed result

The heading said `決済が承認されました`, but the status row displayed the raw
API enum `AUTHORIZED`.

## Impact

The payment amount and state were correct, so there was no financial effect.
However, mixed-language content reduces trust and makes the Japanese checkout
look incomplete. It also breaks the documented localization rule.

## Root cause

The result renderer copied `payment.status` directly from the API response. It
localized the heading but did not map the status value to customer-facing copy.

## Resolution and regression evidence

The renderer now maps approved and declined API states to English or Japanese
display values. Cucumber scenarios assert `Authorized` in English and `拒否` in
Japanese. The Japanese approval journey also verifies the localized result
heading, reference, and amount.

The raw API status remains unchanged and continues to be checked separately at
the API test level.
