# Enhancement 2 Asynchronous Payment Confirmation Scenario Catalog

## Document information

| Field | Value |
|---|---|
| Enhancement | 2: Asynchronous payment confirmation |
| Repository position | After Enhancement 1 and UX-01 are implemented, reviewed, and closed |
| Status | In progress; migration foundation scenarios passed; customer-facing English and Japanese wording remains pending owner review; no asynchronous-confirmation scenario is passed evidence |
| Test basis | [Payment requirements](docs/payment-requirements.md), [risk-based test plan](docs/test-plan.md), and completed idempotency, webhook, and reconciliation evidence from Milestones 4–5 |
| Revision note | Revised after review. Renamed from an earlier "Milestone 9" draft, which incorrectly reused closed milestone numbering and the term "settlement," which already has a distinct meaning in this project |

## Executive summary

Every payment method modeled so far resolves synchronously: a request is
submitted and the platform immediately returns `AUTHORIZED` or `DECLINED`.
This enhancement adds one payment method whose outcome is not known at
request time. The customer is issued a reference and pays through a separate
channel at a later, unpredictable time. The platform learns the outcome
through an asynchronous **payment confirmation**, not through the original
request/response cycle.

This is a distinct concept from the project's existing **settlement**, which
refers to reconciling an external financial batch against captured ledger
entries. This document does not reuse that term. A payment confirmation is
the event that causes a payment to become captured or to be identified as
overdue; settlement and reconciliation continue to mean exactly what they
already mean in this project.

The central risk is not the happy path. It is what happens when a real-world
confirmation does not respect the platform's own expectations: a
confirmation that arrives after the confirmation window has closed, a
duplicate confirmation, a confirmation with a mismatched amount or currency,
or a confirmation for a reference the platform does not recognize. A
platform that silently accepts or silently drops any of these creates a
financial correctness problem or an unresolved support problem.

## Approved entry foundation

Asynchronous confirmation requires several new persisted fields and records.
Before those changes begin, the project must replace its earlier
`create_all()`-only local setup with an explicit versioned migration path. This
dependency was exposed when a current application build opened an older local
database and failed only after the first payment request.

| ID | Situation | Expected result |
|---|---|---|
| `MIG-01` | A new database is initialized | The complete current schema is created and the application starts |
| `MIG-02` | The known older database is upgraded | Missing lifecycle-idempotency and decline fields are added while payment, ledger, webhook, projection, and idempotency evidence remains intact |
| `MIG-03` | The migration command runs twice | The second execution succeeds without changing business data |
| `MIG-04` | The application starts against an outdated database | Startup stops with a useful migration instruction instead of allowing a later HTTP 500 |
| `MIG-05` | The application starts after migration | Health, checkout, and payment creation work normally |
| `MIG-06` | An unknown legacy schema is presented | Migration stops without marking the database current or pretending the service is ready |
| `REG-M01` | Existing synchronous behavior runs after migration support is added | Authorization, decline, capture, refund, idempotency, webhooks, and reconciliation remain unchanged |

The approved operational policy is explicit migration before local service
startup. Startup validates the recorded schema revision and fails early when it
is outdated. It does not silently mutate a persistent database while the HTTP
service is starting. Isolated test factories may continue creating disposable
schemas directly for fast unit and integration feedback.

## Situation

The current domain model supports exactly two synchronous outcomes for a new
request: `AUTHORIZED` or `DECLINED`. No existing state represents "accepted
for processing, outcome not yet known, and will resolve later without another
request to the original payment endpoint."

The current financial model also enforces `captured_amount <= authorized_amount`
as a database-level invariant. A payment method with no card-style
authorization step cannot pass through the existing capture path without
either violating this invariant or introducing a second, method-specific
invariant regime. This document resolves that by capturing through the same
invariant, not around it — see "Confirmed state" below.

## Business risks

| Risk | Possible impact | Priority |
|---|---|---|
| A late confirmation silently captures the payment | A payment is treated as paid without any reviewed decision about whether that is correct | Critical |
| A late confirmation is silently dropped | Real money received by the merchant is never reflected in the platform | Critical |
| A duplicate confirmation creates a second financial effect | Double-captured funds against a single payment | Critical |
| Confirmation and expiry are evaluated concurrently with no defined winner | More than one financial effect could occur for the same payment, or the outcome could depend on timing rather than a rule | Critical |
| A confirmation referencing an unknown payment is silently discarded | The only evidence that money may have arrived is lost | High |
| A confirmation with the wrong amount or currency is accepted | A payment is captured for a different amount than was actually confirmed | High |
| An unsigned or incorrectly signed confirmation can change payment state | An unauthorized caller can mark an unpaid payment as paid | Critical |
| Expiry depends on an implicit passage of time with no operation to apply it | Expired payments never actually transition, or transition inconsistently depending on when they happen to be read | High |
| The new confirmation-timing classification is merged into the existing settlement classification | Two independent dimensions become one confusing field, and the terms "settlement" and "confirmation" become interchangeable in practice even though they mean different things | High |
| A customer who starts a second delayed payment after abandoning the first can pay both open references | Duplicate payment for a single order | Medium |
| Awaiting-payment and expired states are not clearly explained in English and Japanese | A customer does not understand they must complete an offline step, or believes a valid reference has failed | Medium |
| Confirmation payloads or anomaly records retain unnecessary internal detail | Privacy or information-disclosure risk in logs, webhooks, or reports | Medium |

## Scope

### Included

- One new synthetic delayed payment method, provider-neutral in naming.
- A stored `payment_flow` that distinguishes synchronous payments from
  asynchronous-confirmation payments without retaining the synthetic input
  token.
- One new lifecycle state, `AWAITING_PAYMENT`, and one new terminal state,
  `EXPIRED`.
- A unique customer-facing payment reference and deterministic expiry time.
- A durable confirmation inbox with a stable confirmation identity,
  request fingerprint, server receipt time, and disposition.
- Authentication of the confirmation endpoint through the project's existing
  signature-verification approach, with focused positive and negative tests.
- Deterministic, injectable time control for both confirmation receipt and
  expiry, separate from the existing failure-injection mechanism.
- An explicit, idempotent expiry operation.
- A defined outcome for the confirmation/expiry race.
- A defined outcome for unknown-reference, amount-mismatched, and
  currency-mismatched confirmations.
- Cancellation from `AWAITING_PAYMENT`.
- A payment-level confirmation outcome and event-level confirmation
  dispositions, reported independently of existing settlement classification.
- English and Japanese customer-facing messaging for the two new states.

### Outside this enhancement

- Real payment codes or any provider-specific reference format.
- A merchant-facing tool for resolving a late or anomalous confirmation.
  Detection and classification are in scope; a resolution workflow is not.
- Partial confirmation (a confirmed amount lower than the requested amount).
- Rate limiting or abuse protection on the confirmation endpoint. Storing an
  anomaly record for a confirmation referencing an unknown payment is an
  intentional decision favoring not losing evidence, and it is accepted as a
  known, unmitigated cost for this portfolio scope, not an oversight.
- Repeating the full webhook signature, retry, and duplicate-delivery suite.
  The shared delivery mechanism already has dedicated Milestone 5 evidence.
- A third currency.
- Preventing more than one open delayed-payment reference for the same order.
  The current simulator models a merchant reference, not an order aggregate,
  so this risk is explicitly deferred to order-management scope rather than
  claimed as covered.

## Proposed behavior for owner review

### Domain model

- New states: `AWAITING_PAYMENT`, `EXPIRED`.
- A persisted `payment_flow` identifies either `SYNCHRONOUS` or
  `ASYNCHRONOUS_CONFIRMATION`. It is domain metadata, not the synthetic
  payment-method token, which remains unstored.
- An asynchronous-confirmation payment has a generated, unique
  `payment_reference` and an `expires_at` value. These fields are absent for
  synchronous payments.
- `AWAITING_PAYMENT` has `authorized_amount = 0` and `captured_amount = 0`
  and creates no ledger entry, consistent with how `DECLINED` already
  behaves.
- **Confirmed state.** On confirmation before expiry, `authorized_amount`
  and `captured_amount` are set to the confirmed amount in the same atomic
  update, and the payment transitions to `CAPTURED`. This satisfies the
  existing `captured_amount <= authorized_amount` invariant without a
  method-specific invariant, because no intermediate state is ever visible
  where captured exceeds authorized. For this flow, `authorized_amount` is a
  technical balance used to preserve the shared invariant; it does not claim
  that a separate card-style authorization occurred.
- One immutable `CONFIRMATION_CAPTURE` ledger entry is created for the
  confirmed amount. For an `ASYNCHRONOUS_CONFIRMATION` payment,
  reconciliation counts this operation toward both authorized and captured
  ledger totals. This preserves the existing cross-source equality checks
  without inventing an `AUTHORIZATION` entry for an event that did not happen.
- Refunds use the existing `PARTIALLY_REFUNDED` / `REFUNDED` transitions
  unchanged once a delayed payment reaches `CAPTURED`.
- Cancellation from `AWAITING_PAYMENT` is allowed and creates no ledger
  entry, since no funds were ever reserved. A cancelled reference must not
  later be confirmable; a confirmation against a cancelled payment is
  handled as an anomaly, the same as a confirmation against any other
  non-`AWAITING_PAYMENT`, non-`CAPTURED` payment.

### Delayed-payment creation contract

- The existing payment-creation request accepts the provider-neutral synthetic
  token `tok_awaiting_confirmation`.
- The token selects `payment_flow = ASYNCHRONOUS_CONFIRMATION` but is not
  retained after the request fingerprint has been calculated.
- A newly accepted request returns `201 Created`, `AWAITING_PAYMENT`, a unique
  `payment_reference`, and `expires_at = created_at + 30 minutes` using the
  injected server clock.
- An identical payment-creation idempotency replay returns the original
  payment reference and expiry rather than generating a second open reference.
- The checkout presents this as a clearly labelled simulator option and never
  displays the synthetic token.

### Confirmation contract

```json
{
  "confirmation_id": "cnf_...",
  "payment_reference": "ref_...",
  "amount": 2500,
  "currency": "JPY"
}
```

The request uses the same provider-neutral signature-verification pattern as
the existing webhook boundary. A missing or invalid signature is rejected
before a confirmation inbox record, anomaly, lifecycle transition, ledger
entry, or webhook event can be created. This enhancement reuses the shared
security mechanism and adds focused confirmation-endpoint coverage; it does
not repeat the complete webhook security suite.

`received_at` is assigned by the server from an injected clock and is never
trusted from the caller. In this catalog, "received" means the confirmation
has been durably accepted into the confirmation inbox. That durable server
receipt time is the sole time authority:

```text
received_at < expires_at  → on time
received_at >= expires_at → late
```

The limitation is stated explicitly, not left implicit: this cannot
distinguish a physical payment that happened on time from one whose
notification was merely delayed. That distinction is out of scope.

Each accepted confirmation inbox record stores only the fields required for
idempotency, classification, and investigation:

- unique `confirmation_id`;
- request fingerprint;
- `payment_reference`, amount, and currency;
- server-assigned `received_at`;
- final disposition; and
- related payment ID when the reference is known.

The raw signed request body and signature are not retained.

Confirmation cases:

1. **Same `confirmation_id`, same payload.** Idempotent replay of the original
   disposition, whether that disposition was applied or anomalous. No second
   inbox record, anomaly, lifecycle event, or financial effect.
2. **Same `confirmation_id`, different payload.** Rejected as a conflict.
   The original inbox record is unchanged. No new anomaly or financial effect.
3. **New `confirmation_id`, on time, matching amount and currency.**
   Disposition `applied`. Payment transitions to `CAPTURED` as described
   above. One webhook event.
4. **New `confirmation_id`, on time, mismatched amount or currency.**
   Disposition `amount_mismatch` or `currency_mismatch`. Anomaly recorded. No
   financial effect.
5. **New `confirmation_id`, received at or after expiry.** Disposition `late`.
   If the payment is still `AWAITING_PAYMENT`, the same transaction changes it
   to `EXPIRED`, creates its one expiry webhook event, and records the anomaly.
   If it is already `EXPIRED`, its lifecycle state and existing expiry event
   remain unchanged. No financial effect.
6. **New `confirmation_id` for an already-`CAPTURED` payment.** Anomaly
   recorded with disposition `already_resolved`. No second financial effect.
7. **`confirmation_id` referencing an unknown payment.** Recorded as an
   anomaly with disposition `unknown_reference` rather than discarded, so
   evidence that money may have arrived is not lost. No financial effect.
8. **New `confirmation_id` for a cancelled payment.** Anomaly recorded with
   disposition `already_resolved`. No financial effect.

### Confirmation API responses

- A syntactically valid, correctly signed confirmation returns `200 OK` with a
  safe success response after its disposition is durably stored. This includes
  applied,
  late, mismatched, unknown-reference, and already-resolved confirmations, so
  an external sender is not encouraged to retry a permanent business result.
- An identical replay returns the original safe response and an
  `Idempotent-Replay: true` header.
- Reusing a `confirmation_id` with a different payload returns `409 Conflict`.
- A malformed payload returns `422 Unprocessable Entity`.
- A missing or invalid signature returns `401 Unauthorized` and creates no
  stored evidence or effect.
- Customer-facing responses do not expose the internal disposition. The
  stored disposition is available only through the internal diagnostic and
  reconciliation paths.

### Expiry operation

Expiry is an explicit, idempotent operation, not an implicit consequence of
moving a clock forward:

```text
expire_due_payments(now)
```

- Finds every `AWAITING_PAYMENT` payment whose `expires_at <= now`.
- Does not expire a payment that already has a durably accepted, matching,
  on-time confirmation awaiting completion of its lifecycle update.
- Transitions each one to `EXPIRED` exactly once and creates exactly one
  expiry webhook event per payment.
- Is safe to run repeatedly; a payment already `EXPIRED` is not reprocessed.
- Uses the same expiry transition as the late-confirmation path, so the
  scheduler and the confirmation endpoint cannot create separate expiry
  effects.
- The injected clock is a normal dependency of this operation, not part of
  the existing failure-injection mechanism — time control and deliberate
  failure simulation are different concerns and must not share a control
  surface.

### Concurrency

Confirmation and expiry can be invoked concurrently for the same payment.
The durable receipt-time rule decides the outcome; thread scheduling or the
order in which later processing finishes does not change it. An atomic
conditional update, optimistic locking, or an equivalent compare-and-set
protects the lifecycle transition:

- A matching confirmation durably accepted with `received_at < expires_at`
  wins. Expiry must not overwrite it merely because the lifecycle-processing
  transaction finishes later.
- If no on-time confirmation has been durably accepted, expiry can transition
  the payment exactly once when `now >= expires_at`.
- A confirmation durably accepted at or after the boundary is late. It either
  performs the one expiry transition itself or observes the expiry already
  completed.
- At the exact boundary, `received_at >= expires_at` resolves the race in
  favor of expiry.
- Exactly one lifecycle transition and at most one financial effect can
  occur per payment, regardless of arrival order.

### Reconciliation

The existing settlement classification (`matched`, `missing`, `duplicated`,
`amount-mismatched`) is unchanged. Confirmation reporting uses two separate
dimensions because a payment can have one lifecycle outcome and several
confirmation attempts.

```text
payment_confirmation_outcome:
  pending
  confirmed_on_time
  expired_without_on_time_confirmation
  cancelled_unconfirmed

confirmation_disposition:
  applied
  late
  amount_mismatch
  currency_mismatch
  unknown_reference
  already_resolved
```

`payment_confirmation_outcome` belongs to a known delayed payment.
`confirmation_disposition` belongs to one unique confirmation inbox record,
so an unknown reference can be reported without pretending it belongs to a
payment. Replay and ID conflict are request-processing results, not additional
stored dispositions.

Late, mismatched, unknown-reference, and already-resolved anomaly counts and
observed confirmation amounts are reported separately by currency. They are
never added into existing ledger or expected-settlement totals and are never
described as money received by the platform.

Confirmation reporting uses the reconciliation batch cutoff consistently.
Only confirmation records with `received_at <= cutoff` contribute to that
report, and the payment outcome is derived as of the same cutoff. A
confirmation received after the cutoff cannot change an earlier report.

### Lifecycle webhook events

- Creating a delayed payment creates one `PAYMENT_AWAITING` event so the
  merchant projection can observe the initial state.
- Applying an on-time confirmation creates one `PAYMENT_CAPTURED` event.
- Expiry, whether initiated by `expire_due_payments` or a late confirmation,
  creates one `PAYMENT_EXPIRED` event.
- Cancellation creates one `PAYMENT_CANCELLED` event.
- Replays, mismatches, unknown references, and confirmations for an already
  resolved payment do not create another lifecycle event.

### Customer presentation

- The checkout shows an awaiting-payment view with the reference and expiry
  deadline, and an expired view, both in English and Japanese.
- Exact wording, including how the expired view avoids implying a physical
  payment was lost, needs owner review before implementation — the same
  review step already used for decline messaging.
- No internal state name, confirmation identity, or anomaly classification
  is shown to the customer.

## Test-level strategy

| Test level | Planned evidence |
|---|---|
| Unit | Receipt-time comparison; payment-outcome and event-disposition rules as pure functions; asynchronous confirmation transition; `CONFIRMATION_CAPTURE` ledger-total interpretation |
| API | Accepting a delayed request returns `AWAITING_PAYMENT`, reference, and expiry; creation replay returns the original reference; all eight confirmation cases and their safe HTTP contracts; cancellation behavior |
| Integration | Unique reference and confirmation-inbox persistence; one `CONFIRMATION_CAPTURE` entry only after an applied confirmation; zero ledger entries after expiry, mismatch, unknown reference, or cancellation; refunds work unchanged after delayed capture |
| Idempotency | Same-`confirmation_id` replay is idempotent for applied and anomalous dispositions, including concurrent delivery |
| Concurrency | The durable receipt-time rule wins over processing order; exactly one outcome occurs before, at, and after the boundary |
| Security | Valid signatures are accepted; missing or invalid signatures create no inbox record, anomaly, transition, ledger entry, or webhook event |
| Webhook | Awaiting, captured, expired, and cancelled lifecycle events are created once; late confirmation cannot duplicate the expiry event |
| Reconciliation | Payment outcome and event dispositions are reported independently of settlement classification; `CONFIRMATION_CAPTURE` preserves ledger agreement; JPY/USD totals remain separate |
| Browser | Awaiting-payment and expired views render correctly in English and Japanese |
| Exploratory | Whether messaging could mislead a customer about the safety of their money, at desktop and mobile widths |
| Privacy | Confirmation payloads, logs, and anomaly records contain no unnecessary internal identifiers |

## Scenario summary

| ID | Situation | Expected result | Priority | Level |
|---|---|---|---|---|
| `CONF-01` | A delayed request is accepted | `AWAITING_PAYMENT`, unique reference, deterministic `expires_at`, zero financial effect, one awaiting event | High | API and integration |
| `CONF-02` | Confirmation arrives on time with matching amount and currency | Atomic transition to `CAPTURED`; one `CONFIRMATION_CAPTURE` entry; one captured event | Critical | Integration |
| `CONF-03` | No confirmation arrives before expiry | `expire_due_payments` transitions to `EXPIRED`; zero financial effect; one webhook event | Critical | Integration |
| `CONF-04` | An identical delayed-payment creation request is replayed | Original payment ID, reference, and expiry are returned; no second open reference or awaiting event | Critical | API and integration |
| `LATE-01` | A late confirmation finds the payment already `EXPIRED` | Remains `EXPIRED`; one late disposition exists; no duplicate expiry event or financial effect | Critical | Integration |
| `LATE-02` | A late confirmation finds the payment still `AWAITING_PAYMENT` | Atomically expires it, records the late disposition, and creates the one expiry event; no financial effect | Critical | Integration |
| `DUP-01` | Same applied `confirmation_id` and payload replay | Original safe response is replayed; no second inbox record, ledger entry, or webhook event | Critical | Integration |
| `DUP-02` | Same `confirmation_id`, different payload | Rejected as a conflict; no financial effect | Critical | API |
| `DUP-03` | Same anomalous `confirmation_id` and payload replay | Original anomaly disposition is replayed; no duplicate anomaly or other effect | High | Integration |
| `MISM-01` | New `confirmation_id`, on time, wrong amount | Accepted as a permanent anomaly; `amount_mismatch` stored; no financial effect | High | API and integration |
| `MISM-02` | New `confirmation_id`, on time, wrong currency | Accepted as a permanent anomaly; `currency_mismatch` stored; no financial effect | High | API and integration |
| `UNK-01` | `confirmation_id` references an unknown payment | `unknown_reference` anomaly recorded rather than discarded | High | API and integration |
| `CAP-01` | New confirmation for an already-`CAPTURED` payment with a different `confirmation_id` | Anomaly recorded; no second financial effect | Critical | Integration |
| `RACE-01` | Confirmation and expiry are triggered concurrently before, at, and after the boundary | Durable receipt time determines exactly one transition and at most one financial effect | Critical | Concurrency |
| `CANC-01` | A payment is cancelled while `AWAITING_PAYMENT` | No ledger entry; one cancelled event; a later confirmation receives `already_resolved` | Medium | API and integration |
| `SEC-C01` | A correctly signed confirmation is submitted | It is authenticated and evaluated normally | Critical | API |
| `SEC-C02` | A missing or invalid confirmation signature is submitted | `401`; no confirmation record, anomaly, lifecycle change, ledger entry, or webhook event | Critical | API and integration |
| `REC-C01` | A reconciliation batch includes confirmed, expired, late, mismatched, unknown, and already-resolved cases | Payment outcomes and event dispositions are correct and independent of settlement classification | High | Unit and integration |
| `REC-C02` | JPY and USD delayed totals are reconciled together | Totals remain reported separately by currency | Medium | Integration |
| `REC-C03` | A delayed payment is captured through `CONFIRMATION_CAPTURE` | Payment, ledger, webhook projection, and external settlement sources agree | Critical | Integration |
| `REC-C04` | A confirmation is received after the reconciliation cutoff | It does not change the payment outcome or anomaly totals reported as of that cutoff | High | Integration |
| `LOC-C01` | Awaiting-payment and expired views are checked in both languages | Reference, deadline, and status guidance are present, correct, and do not imply lost funds incorrectly | Medium | UI unit and browser |
| `PRIV-C01` | Confirmation payloads, logs, and anomaly records are inspected | No unnecessary internal identifier or raw payload is exposed beyond what reconciliation needs | Medium | Cross-layer |

## Detailed critical scenario: RACE-01

### Business risk

Confirmation and expiry are two independent triggers that can act on the
same payment. Without a defined winner, the outcome could depend on
processing order or timing rather than a rule, and more than one financial
effect could occur for a single payment.

### Preconditions

- A payment exists in `AWAITING_PAYMENT` with a known `expires_at`.
- The injected clock and confirmation receipt time are both controllable by
  test code.
- The test can pause lifecycle processing after the confirmation has been
  durably accepted, independently from the expiry operation.

### Steps

1. Durably accept a matching confirmation strictly before `expires_at`, pause
   its lifecycle processing, and invoke `expire_due_payments` with `now` at or
   after `expires_at`.
2. Resume confirmation processing and repeat with the processing order
   reversed.
3. Repeat with no durably accepted on-time confirmation and allow expiry to
   run at the deadline.
4. Submit confirmations durably accepted exactly at and strictly after
   `expires_at`.

### Expected result

- An on-time, durably accepted matching confirmation results in `CAPTURED`
  with one `CONFIRMATION_CAPTURE` entry even when its lifecycle processing
  resumes after the expiry operation.
- When no on-time confirmation was durably accepted, exactly one expiry
  transition and expiry event occur.
- At the exact boundary, the payment resolves to `EXPIRED` and the
  confirmation is treated as late.
- No ordering produces two financial effects or leaves the payment in an
  ambiguous state.

### Planned evidence

- A concurrency-focused integration test exercising both processing orders
  and the before/at/after boundary cases, asserting that durable receipt time
  produces one deterministic outcome each time.

## Browser acceptance example

```gherkin
Scenario Outline: Awaiting-payment guidance follows the selected language
  Given the checkout is displayed in "<language>"
  And the customer selects the delayed payment method
  When the customer submits the request
  Then the payment is shown as awaiting payment
  And the reference and deadline are displayed in "<language>"
  And no internal state name is displayed

  Examples:
    | language |
    | English  |
    | Japanese |
```

## Planned implementation sequence

1. Add the persisted payment flow, unique payment reference, expiry time,
   `AWAITING_PAYMENT` / `EXPIRED` states, and initial awaiting webhook event.
   Tests: `CONF-01`, `CONF-04`.
2. Add the signed confirmation contract, durable inbox,
   `confirmation_id`-based idempotency, safe response contract, and focused
   signature checks. Tests: `DUP-01`, `DUP-02`, `DUP-03`, `SEC-C01`,
   `SEC-C02`.
3. Add the atomic confirmation transition and `CONFIRMATION_CAPTURE` ledger
   interpretation. Tests: `CONF-02`, `REC-C03`.
4. Add `expire_due_payments` and the shared late-confirmation expiry path with
   injected time. Tests: `CONF-03`, `LATE-01`, `LATE-02`.
5. Add anomaly dispositions for mismatched, unknown-reference,
   already-captured, and cancelled confirmations. Tests: `MISM-01`,
   `MISM-02`, `UNK-01`, `CAP-01`.
6. Add durable-receipt-time race resolution with an atomic conditional
   lifecycle update. Tests: `RACE-01`.
7. Add cancellation and its lifecycle event. Tests: `CANC-01`.
8. Extend reconciliation with separate payment outcomes, event dispositions,
   currency-separated anomaly reporting, and cutoff behavior. Tests:
   `REC-C01`, `REC-C02`, `REC-C03`, `REC-C04`.
9. Add English and Japanese messaging, pending owner review of exact
   wording. Tests: `LOC-C01`.
10. Run the privacy checks and a focused exploratory session on whether the
    stored evidence is minimal and whether messaging could mislead
    a customer about the safety of their money.
11. Run the complete project gate and write the closing quality report.

## Decisions carried into this revision

| Decision | Resolution |
|---|---|
| Terminology | "Payment confirmation" and "confirmation anomaly"; "settlement" is reserved for its existing meaning |
| Repository position | Enhancement 2, after Enhancement 1 is fully closed |
| Flow identity | Persist `payment_flow`; continue not storing the synthetic input token |
| Delayed simulator input | Use `tok_awaiting_confirmation`; generate a unique reference and a 30-minute expiry from the injected clock |
| Confirmed state | Reuse `CAPTURED`; set both amount balances atomically and record one `CONFIRMATION_CAPTURE` ledger effect |
| Confirmation identity | Durable inbox record keyed by `confirmation_id`; identical replay returns the original result and conflicting reuse returns `409` |
| Endpoint security | Reuse provider-neutral signature verification; reject missing or invalid signatures before storing or changing anything |
| Time authority | Durable server receipt time; receipt at the deadline is late |
| Expiry mechanism | Explicit, idempotent `expire_due_payments(now)` plus the same expiry transition in the late-confirmation path |
| Concurrency | Durable receipt time determines the result; atomic conditional updates prevent duplicate transitions and effects |
| Unknown reference | Store an `unknown_reference` disposition; rate limiting remains an explicit portfolio limitation |
| Amount/currency mismatch | Store distinct dispositions; no financial effect and no retry-inducing error response |
| Reconciliation | Separate payment outcome from per-confirmation disposition; keep both independent of settlement classification |
| Reconciliation cutoff | Include confirmation evidence only through the batch cutoff; later confirmations cannot rewrite an earlier report |
| Lifecycle events | Awaiting, captured, expired, and cancelled states each produce one event; anomalies and replays do not |
| Cancellation | Allowed from `AWAITING_PAYMENT`; no ledger entry; later confirmation receives `already_resolved` |
| Duplicate open references | Explicitly deferred to an order-management model outside this enhancement |

## Note carried from Enhancement 1

The unresolved Enhancement 1 decision — whether legacy `tok_declined` remains
an alias for `unknown` — is unrelated to this enhancement and should be
closed before or independently of this one.
