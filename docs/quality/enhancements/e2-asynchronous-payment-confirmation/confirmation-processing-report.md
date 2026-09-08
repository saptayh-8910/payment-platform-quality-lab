# Enhancement 2 Confirmation Processing Report

## Document information

| Field | Value |
|---|---|
| Enhancement | 2: Asynchronous payment confirmation |
| Slice | Signed confirmation, final classification, and atomic capture |
| Result | Ready to merge; full pull-request CI passed |
| Branch | `codex/e2-confirmation-processing` |
| Pull request | [#22](https://github.com/saptayh-8910/payment-platform-quality-lab/pull/22) |
| Local execution date | 2026-09-09 |

## Executive summary

The service now accepts a signed confirmation for a payment that was created
earlier. A valid matching confirmation changes the payment from
`AWAITING_PAYMENT` to `CAPTURED` in one database transaction. The same
transaction stores the confirmation, creates one financial ledger entry, and
creates one captured webhook event.

The difficult cases do not silently disappear. Late, mismatched, unknown, and
already-resolved confirmations receive a durable internal disposition. They all
return the same small external acknowledgement, so the endpoint does not reveal
whether a payment reference exists or what state it has.

## Business decision exposed during implementation

The earlier implementation sequence separated signed intake from final payment
processing. That would have published an endpoint capable of accepting a
confirmation without being able to give it a final disposition. The reviewed
slice was therefore implemented as one end-to-end boundary. Every authenticated,
valid request now finishes as applied or as a named anomaly before success is
returned.

This change does not add the scheduled expiry operation or claim that the
confirmation-versus-expiry race is proven. Those remain separate high-risk
work.

## Implemented controls

- `POST /payment-confirmations` verifies `Confirmation-Signature` against the
  exact raw body before parsing or persistence.
- The endpoint uses a separate synthetic confirmation secret while reusing the
  tested timestamped HMAC-SHA256 mechanism.
- The server assigns `received_at` from an injected, timezone-aware clock.
- A durable inbox record keeps the confirmation ID, request fingerprint,
  reference, amount, currency, receipt time, final disposition, related payment
  ID when known, and the safe response snapshot.
- The raw signed body and signature are not retained.
- A matching on-time confirmation sets authorized and captured amounts together
  and records one `CONFIRMATION_CAPTURE` ledger entry.
- Payment state, inbox evidence, ledger entry, and captured event commit or roll
  back together.
- Equivalent replay returns the stored acknowledgement and the existing
  `Idempotent-Replayed: true` response header.
- Conflicting reuse of a confirmation ID returns `409` and preserves the first
  result.
- `GET /internal/payment-confirmations/{confirmation_id}` provides queryable
  support evidence independently of the current payment state.
- Reconciliation interprets `CONFIRMATION_CAPTURE` once for both authorized and
  captured totals, preserving the shared balance comparison.

## Scenario results

| Scenario | Result | Main evidence |
|---|---|---|
| `SEC-C01` valid signature | Passed | Exact signed body reached normal processing |
| `SEC-C02` invalid signature | Passed | Missing, malformed, stale, future, and incorrect signatures produced no stored or financial effect |
| `CONF-02` matching on-time confirmation | Passed | One atomic capture, ledger entry, version change, and event |
| `DUP-01` applied replay | Passed | Original safe result returned; counts remained unchanged |
| `DUP-02` conflicting identity reuse | Passed | `409`; original payment, evidence, ledger, and events remained unchanged |
| `DUP-03` anomalous replay | Passed | Original anomaly evidence was reused without duplication |
| `MISM-01` amount mismatch | Passed | Internal `amount_mismatch`; no financial effect |
| `MISM-02` currency mismatch | Passed | Internal `currency_mismatch`; no financial effect |
| `UNK-01` unknown reference | Passed | Queryable evidence with no payment foreign key |
| `CAP-01` already captured | Passed | Internal `already_resolved`; no second capture |
| `LATE-01` already expired | Passed | Separate late evidence; no additional expiry event |
| `LATE-02` late while awaiting | Passed | One expiry transition and event; zero financial effect |
| `REC-C03` cross-source agreement | Passed | Payment, ledger, webhook projection, and settlement report matched |
| `PRIV-C01` minimal evidence | Passed | No raw signature, secret, or complete raw body retained |

## Automated evidence

| Evidence | Result |
|---|---|
| Complete Python suite | 316 passed |
| Branch-aware coverage | 86.40%; required minimum 85% |
| Confirmation-focused unit, API, integration, migration, and reconciliation tests | Passed |
| Node unit suite | 45 passed |
| TypeScript check | Passed |
| Cucumber-JS and Chromium regression | 11 scenarios and 100 steps passed |
| Ruff lint and formatting | Passed |
| Database migration on a copy of the local schema | Upgraded to `0004_confirmations`; existing local database untouched |
| Git diff check | Passed |
| GitHub Actions pull-request gate | Six checks passed across Python, Chromium, and performance workflows |

## Financial and privacy evidence

The applied path creates one positive ledger entry. It sets authorized and
captured totals to the same confirmed amount, so it preserves the existing
`captured_amount <= authorized_amount` invariant without selecting a different
rule through `payment_flow`.

Every anomalous path leaves ledger counts unchanged. The atomic rollback test
forces captured-event creation to fail after the payment and ledger changes are
staged. The transaction restores the awaiting payment and leaves no confirmation
or ledger record behind.

The external response is always `{"accepted": true}` after a valid request has
received a durable disposition. It does not expose payment existence, internal
state, anomaly type, or financial totals. Diagnostic evidence is separated from
that sender-facing contract.

## Limitations and remaining risk

- The explicit `expire_due_payments` operation is not implemented. A payment can
  currently reach `EXPIRED` only when a late confirmation arrives.
- The high-risk confirmation-versus-expiry race has not been forced or proven.
- Cancellation from `AWAITING_PAYMENT` remains unimplemented.
- Confirmation dispositions are not yet included in the expanded reconciliation
  summary or its cutoff calculations. This slice proves only the existing
  cross-source financial agreement for an applied confirmation.
- English and Japanese awaiting/expired guidance is not implemented.
- The diagnostic endpoint is an internal simulator surface. It does not claim
  production authentication or authorization controls.
- Signature rate limiting and abuse protection remain outside the approved
  portfolio scope.
- Server receipt time cannot prove when a physical payment happened. It proves
  only when the platform durably received the confirmation.

## Recommendation

Proceed to merge this slice. The evidence supports signed
confirmation, replay safety, final classification, atomic financial capture,
and preserved cross-source agreement. Do not describe Enhancement 2 as complete
until scheduled expiry, the forced race, cancellation, reconciliation expansion,
localized messaging, exploratory testing, and the closing report are finished.

## Next review

Review `CONF-03` for the explicit scheduled expiry operation. The next slice
must reuse the same expiry transition rather than create a second path with
different webhook or financial behavior.
