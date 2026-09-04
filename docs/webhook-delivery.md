# Webhook Delivery and Consumption

## Purpose

Webhooks tell a merchant system that a payment changed. Delivery is at least
once. This means the same event may arrive more than once, even when both systems
work correctly. The consumer must treat duplicate delivery as a normal recovery
case.

This simulator uses synthetic data and an in-process consumer. It does not call
a real merchant or send data over the internet.

## Transactional outbox

Each accepted payment version creates one webhook event in the same transaction
as the payment, ledger entry, idempotency result, and response snapshot.

If event persistence fails, the complete financial transaction rolls back. If a
client retries a committed payment request, the original event is reused and no
second event is created.

The event types are:

- `payment.authorized`
- `payment.confirmation_requested`
- `payment.declined`
- `payment.captured`
- `payment.cancelled`
- `payment.refunded`

Partial and full refunds share one event type. The full payment snapshot shows
the current refund total and status.

`payment.confirmation_requested` means delayed-payment instructions were
accepted and later confirmation is expected. Its completed-action name follows
the other event names. It does not imply that every payment creation emits a
generic creation event.

## Event body

Each event contains:

- a unique event ID;
- event type and UTC creation time;
- payment ID and aggregate version;
- full payment status and integer minor-unit totals; and
- payment flow plus the reference and expiry for asynchronous payments; and
- the normalized decline reason for a declined payment, or `null` for every
  non-declined payment.

The payload does not contain the submitted synthetic payment token or signing
secret. The consumer validates that a declined snapshot has one recognized
reason and that a non-declined snapshot has no reason.

## Signature

The producer signs `timestamp.raw_body` with HMAC-SHA256. The consumer checks the
exact bytes before parsing JSON. Changing an amount, status, version, or even the
body formatting after signing invalidates the signature.

The timestamp must be within five minutes of the consumer clock. The test secret
is synthetic and is not included in payloads or reports.

## Delivery state

```text
PENDING → PROCESSING → DELIVERED
    ↑          │
    └── retry ─┘

PENDING → PROCESSING → EXHAUSTED
```

An atomic lease allows one dispatcher to own an active attempt. An expired lease
can be claimed later if a worker stops unexpectedly.

The retry schedule is deterministic:

1. First attempt immediately.
2. Second attempt one second after the first failure.
3. Third attempt five seconds after the second failure.

Every non-success response, timeout, or connection failure follows the same
three-attempt limit. Tests use an injected clock and do not wait in real time.

## Consumer inbox and projection

The consumer stores each processed event ID and updates a separate merchant
payment projection in one transaction.

- The same event ID and body returns a safe duplicate result.
- The same event ID with different content is an event collision.
- A higher payment version updates the projection.
- A lower version is stored as stale and cannot replace newer state.
- A higher version can be applied when an earlier version is missing because the
  event contains a full snapshot. The version gap remains visible.
- Conflicting content for the same payment version is rejected.
- The projection preserves the normalized decline reason so the payment and
  merchant view can be compared without retaining the submitted token.

Webhook consumption never changes the source payment or financial ledger.

## Acknowledgement-loss recovery

The centerpiece test models this sequence:

1. Consumer verifies and commits an event.
2. Producer loses the successful acknowledgement.
3. Producer records a timeout and schedules a retry.
4. The same event is delivered again.
5. Consumer recognizes the event ID and returns success without applying it
   again.
6. Producer marks the event as delivered.

The final database contains one payment effect, one processed event, and one
merchant projection update.

## HTTP endpoints

| Endpoint | Purpose |
|---|---|
| `GET /webhooks/events` | List outbox events and delivery state |
| `GET /webhooks/events/{id}/attempts` | Show delivery attempt history |
| `POST /webhooks/events/{id}/deliver` | Run one in-process delivery attempt |
| `POST /webhook-consumer` | Receive and verify a signed raw event body |
| `GET /merchant-projections/{payment_id}` | Read the consumer-built payment view |

The `Webhook-Signature` header carries the timestamped signature.

Test-only delivery and consumer failure headers return `403` unless the
application explicitly enables failure injection.

## Focused evidence

```bash
python -m pytest \
  tests/unit/test_webhook_signatures.py \
  tests/integration/test_webhook_delivery.py \
  tests/api/test_webhooks.py
```

The implementation also records the genuine timestamp defect found while
testing the atomic delivery lease: [DEF-003](defects/DEF-003-webhook-lease-datetime-comparison.md).

Settlement generation and reconciliation remain the next Milestone 5 slice.
