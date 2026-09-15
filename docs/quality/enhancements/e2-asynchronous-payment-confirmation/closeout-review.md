# E2 consolidated closeout review

Status: Design decisions and scenarios approved on 2026-09-14; execution recorded in [closing report](closing-report.md).
Baseline: main `67f3d64` after PR #25. Date: 2026-09-14.
Delivery: work locally; one milestone push and PR after local verification.

## Remaining business outcome

Explain what happened to delayed payments, separate suspicious confirmation
attempts from money, and show customers clear awaiting and expired views.
Close E2 with reproducible automated and exploratory evidence, not only a
list of implemented features.

## Verified gaps and a reporting decision

The current reconciliation service reads current payment/projection state and
cutoff-filtered ledger entries. It is not an immutable historical snapshot of
everything known at the cutoff. Final confirmation records have received_at,
but no completion timestamp. Recovery can finish an old pending receipt later.
The checkout currently renders every non-AUTHORIZED result as a decline.

The catalog requires that confirmations received after the cutoff cannot change
an earlier confirmation report. Receipt time alone does not solve the separate
case of an old pending receipt completed later.

### Proposed reporting contract for approval

Keep existing settlement classifications and current source-health checks
unchanged. Add a separately identified confirmation report section with its own
cutoff semantics; do not label the entire existing reconciliation output as an
immutable historical report.

Recommended: persist the confirmation section when first generated for a batch.
Record both cutoff and generated_at. Later reads return that saved section;
a newly generated batch can report newly available evidence using the same
cutoff. Label it as evidence available at generation for receipts through the
cutoff, not as an exact reconstruction of knowledge at the cutoff.

This is an explicit clarification of the original as-of wording. It requires
a small schema migration for the saved section. Existing batches get a section
on first generation, not a fabricated historical snapshot. Do not backdate
generation times. Concurrent first-generation requests must save one result.

Tradeoff: a saved report can show pending work that has since completed. The
generation timestamp and a new-batch workflow make that limitation visible.
An alternative is true historical processing-time reporting, which requires
new completion evidence and historical-data rules; it is not assumed here.

For the new section:

- Include delayed payments created through cutoff; derive their effective
  lifecycle outcome through cutoff from stored lifecycle evidence, not today's
  mutable payment status. Ignore later effective transitions.
- Retain the four catalog outcomes: pending, confirmed_on_time,
  expired_without_on_time_confirmation, cancelled_unconfirmed.
- Include final dispositions only for unique receipts received through cutoff
  and completed by generation. Show unresolved receipt count separately; never
  invent a final disposition for pending work.
- Keep unknown references independent of known payments. Count replay once;
  ID conflicts are not new stored dispositions.
- Separate anomaly counts and observed amounts by submitted currency. These
  amounts are evidence, not captured funds, and never enter settlement totals.
- State explicitly that later recovery may appear in a new report generation,
  but cannot mutate the saved confirmation section for the original batch.

## Reporting scenarios for review

| Case | Business check | Evidence |
|---|---|---|
| R1 / REC-C01 | Mixed pending, confirmed, expired and cancelled payments | Each eligible payment has one outcome; outcome counts reconcile to eligible payment count |
| R2 / REC-C01 | Applied, late, mismatched, unknown and already-resolved receipts | Dispositions are independent of payment outcome; unknown references are not dropped |
| R3 / REC-C02 | Mixed JPY and USD anomalies | Counts and observed amounts stay separate by submitted currency; no conversion or combined money total |
| R4 / REC-C03 | Captured delayed payment and refund | Existing ledger/settlement comparisons remain correct; anomalies add no financial amount |
| R5 / REC-C04 | Receipt before, exactly at, and after cutoff | Inclusive boundary; after-cutoff receipt excluded from the section |
| R6 / REC-C04 | Payment cancelled, expired, captured or refunded after cutoff | Later current state does not rewrite the effective outcome through cutoff |
| R7 | On-time receipt pending at generation, then recovered | Original saved section unchanged; new batch reveals completion; both generation times shown |
| R8 | Replay or ID conflict | No extra receipt/disposition count or observed amount |
| R9 | Two readers first generate the same section concurrently | One saved section; both return the same result; no partial snapshot |
| R10 | Migration and failed snapshot write | Existing financial data preserved; no invented past report; failure leaves no partial section |
| R11 / PRIV-C01 | Inspect report contract | No signatures, raw request bodies or unnecessary internal identifiers |

## Proposed customer copy for approval

All views retain the test-environment warning. The reference below is the
generated payment reference, not the merchant's order reference. Deadline
display uses an explicit Asia/Tokyo timezone in both languages; tests use
injected times, not the browser's machine timezone.

| View | English | Japanese |
|---|---|---|
| Awaiting title | Waiting for payment confirmation | お支払いの確認待ちです |
| Awaiting guidance | Keep this reference. This test payment is waiting for confirmation. Do not make a real payment. | この参照番号を控えてください。このテスト決済は確認待ちです。実際の支払いはしないでください。 |
| Reference label | Payment reference | 決済参照番号 |
| Deadline label | Confirmation deadline (Japan time) | 確認期限（日本時間） |
| Refresh action | Check payment status | 支払い状況を確認 |
| Expired title | Payment request expired | 支払いリクエストの期限が切れました |
| Expired guidance | This request has expired. If you already paid, contact support with your reference before trying again. This simulator does not process real payments. | このリクエストは期限切れです。すでに支払いをした場合は、再度支払う前に参照番号を添えてサポートにお問い合わせください。このシミュレーターでは実際の決済は行いません。 |
| Confirmed title | Payment confirmed | お支払いを確認しました |
| Confirmed guidance | This test payment has been confirmed. No real money was processed. | このテスト決済の確認が完了しました。実際のお金は処理されていません。 |
| Cancelled title | Payment request cancelled | 支払いリクエストはキャンセルされました |
| Cancelled guidance | This request was cancelled. If you already paid, contact support with your reference. | このリクエストはキャンセルされました。すでに支払いをした場合は、参照番号を添えてサポートにお問い合わせください。 |
| Refresh failure | We could not check the latest status. The result below may be out of date. Try checking again. | 最新の状況を確認できませんでした。以下の結果は最新ではない可能性があります。もう一度確認してください。 |

Japanese copy is a proposed draft, not a claim of native-language review.

## UI scenarios for review

| Case | Required behaviour |
|---|---|
| U1 / LOC-C01 | Delayed simulator outcome creates awaiting view in EN and JA with exact reference, amount and explicit-zone deadline |
| U2 | Manual status refresh uses GET only; never creates another payment or confirmation; duplicate clicks are disabled while fetching |
| U3 | Backend confirmation, expiry and cancellation each refresh into their dedicated view; no raw state or anomaly code appears |
| U4 | Client clock passing deadline alone does not claim backend EXPIRED; status comes from the API |
| U5 | Language change keeps reference, amount and deadline unchanged and performs no network request |
| U6 | Reload restores the delayed payment and simulator outcome correctly; no new POST or idempotency key |
| U7 | Refresh failure preserves last known result, explicitly marks it potentially stale and permits another check |
| U8 | Desktop and 390x844 EN/JA views have no overlap or horizontal overflow; keyboard focus and live announcements remain usable |
| U9 | New test clears old reference/result; existing synchronous and decline journeys remain covered |

No automatic polling, customer cancellation button, or browser-held signing
secret. Tests arrange confirmation/expiry through trusted test setup. No new
UI controls for refunds are included; existing supported restore states must
not regress or be incorrectly relabelled as declines.

## Local completion and single-push gate

1. Review the reporting rules, test scenarios, and customer messages above
   before implementation. Completed in the recorded 2026-09-14 review.
2. Implement reporting and tests, then UI and tests, in local commits.
3. Execute exploratory charter: awaiting to confirmed/expired/cancelled,
   refresh failure, reload, language switch, keyboard and mobile layouts.
   Record build, environment, steps, expected/observed results, screenshots,
   defects and retests. Mark any unexecuted checks honestly.
4. Run complete Python, Node, TypeScript, browser, formatting and performance
   gates. Update README, traceability and E2 closing report with actual evidence.
5. Push the completed milestone once and open one PR. CI still runs remotely;
   if it reveals a failure, report it before any corrective push. Do not weaken
   gates to maintain a one-push count.

Both original local reference catalogs remain untouched and untracked.
