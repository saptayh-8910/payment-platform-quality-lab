# DEF-006: Refresh removed uncertain-payment recovery

## Summary

The checkout lost its uncertain result and Retry action when the browser was
refreshed after a payment committed but its response was lost. The server kept
the original payment and idempotency result, but the browser displayed a blank
form without explaining that a payment might already exist.

## Detection

| Field | Evidence |
|---|---|
| Milestone | 7: Structured exploratory testing and defect evidence |
| Found by | Charter `M7-S01`, state and interrupted-communication exploration |
| Affected requirement | M6 `REL-04` and `REL-05`: an uncertain result remains honest and retries with the same key |
| Severity | High |
| Status | Resolved before milestone close |

## Reproduction

1. Open the controlled checkout with failure injection enabled.
2. Enter a synthetic reference and JPY amount.
3. Make the server commit the payment but lose the first response.
4. Confirm that the checkout shows an uncertain result and Retry action.
5. Refresh before selecting Retry.
6. Observe the checkout state.
7. Enter different synthetic details and submit again.

The result was reproduced with both Japanese and English checkout content on
separate temporary databases.

## Expected result

Refresh should keep enough tab-scoped recovery state to show the uncertain
result. Retry should resend the original financial request with the same
idempotency key. A customer should not be invited to start an unrelated request
while the old key is still active.

## Observed result

Refresh displayed a blank form and removed the Retry action. The old active
idempotency key remained in `sessionStorage`. Submitting different details then
reused that key, so the API correctly rejected the conflict and the checkout
showed a general error.

## Impact

The customer lost the only visible path back to a payment that already existed.
The later error did not explain which payment had committed or why the new
details failed. This could create customer confusion and a support case.

No duplicate financial effect occurred. Each reproduction still contained one
payment, one authorization ledger entry, one idempotency claim, and one webhook
event.

## Root cause

The checkout persisted the active idempotency key, but it kept the uncertain
state and original request details only in page memory. Page refresh cleared
that memory. Startup restored only completed results with a known payment ID, so
an active key without a completed response became an invisible stale state.

## Resolution

The checkout now stores a minimal active retry packet in tab-scoped
`sessionStorage` before sending the request. It contains only the synthetic
reference, integer amount, currency, and `approve` or `decline` choice. The raw
API token is not stored.

On refresh, a valid packet and active key restore the original form data and
uncertain result. Retry sends the same financial request with the same key.
Successful or definite error responses clear the active packet. New checkout
also clears it. Incomplete, malformed, or out-of-range stored values are
discarded instead of being used.

## Regression evidence

The critical Cucumber scenario now refreshes while the Japanese result is still
uncertain. It checks that the uncertain message and Retry action remain, retries
the payment, and proves:

- the committed payment ID is returned;
- both payment requests use the same idempotency key;
- refresh after completion keeps the same payment;
- only one authorization ledger entry exists; and
- only one webhook event exists.

Manual follow-up repeated the exact failing sequence after the fix. The
uncertain Japanese result survived refresh, Retry returned the original JPY
2,500 authorization, and the database still contained one ledger and webhook
effect.
