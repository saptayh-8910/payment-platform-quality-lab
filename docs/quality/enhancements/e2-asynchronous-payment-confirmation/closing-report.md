# E2 asynchronous payment confirmation: closing quality report

Date: 2026-09-14. Status: Local completion verified; remote CI pending at creation.
Branch: `codex/e2-milestone-closeout`. Starting baseline: `67f3d64`.
Reviewed scope: [closeout decisions and scenarios](closeout-review.md).

## Business situation

Some payments are created now and confirmed later. A request can remain open
while a confirmation is delayed, duplicated, incorrect, or missing. A checkout
must not call that a decline, and a report must not count an attempted amount
as captured money.

E2 now connects creation, authenticated confirmation, expiry, race protection,
recovery, cancellation, reporting, and customer guidance. This is a privacy-safe
simulator with synthetic data, not a real payment processor.

## Why these tests

The highest risks are duplicate financial effects, losing accepted work, and
showing misleading status. Domain/API/integration tests inspect persisted
evidence. Forced independent-connection races establish ordering rather than
relying on sequential calls. Browser tests check the actual interface against
the running backend. Visual inspection checks issues that passing text
assertions alone can miss.

Earlier slices retain their own evidence:

- [Migration foundation](migration-foundation-report.md).
- [Confirmation processing](confirmation-processing-report.md).
- [Scheduled expiry](scheduled-expiry-report.md).
- [Race and recovery](race-resolution-report.md).
- [Awaiting cancellation](cancellation-report.md).

Their historical test counts and stated future work are not the current status.

## Reporting decision and outcome

The new `confirmation_section` is saved once per settlement batch. It describes
effective-through-cutoff evidence available at generation. It has both cutoff
and generation timestamps. It is not an exact reconstruction of everything
known at the cutoff. Existing financial comparisons remain live and separate.

This distinction matters because an accepted receipt can finish processing
later. The first report may correctly show pending work. Recovery cannot
rewrite that saved section; a new batch can show the updated evidence. The
small `0006_reports` migration adds empty report storage without inventing
historical snapshots. No financial records are altered by report generation.

Unknown references remain independent of payments. Each final receipt has one
disposition; replay and ID conflict add none. Observed anomaly amounts are
separate by submitted currency and explicitly are not money received.

## Closeout evidence mapping

| Reviewed cases | Evidence and result |
|---|---|
| R1–R2 | Mixed pending/confirmed/expired/cancelled outcomes and applied/late/mismatch/unknown/already-resolved dispositions; tests pass |
| R3 | JPY and USD observed anomalies remain separate; exact counts and amounts asserted |
| R4 | Existing confirmation-capture, refund, ledger and settlement regressions pass; financial calculation is unchanged |
| R5–R6 | Before/at/after cutoff and later terminal-state tests prevent current status from rewriting cutoff outcomes |
| R7 | Save while pending, recover, reread unchanged original, generate fresh batch with completion |
| R8 | Identical replay and changed-payload conflict do not inflate report counts |
| R9 | First generator pauses while another connection attempts writer admission; both return the same saved section |
| R10 | Migration repeatability and injected commit failure preserve old data and prevent partial reports |
| R11 | Public section has aggregate evidence, not raw bodies, signatures, fingerprints or payment/confirmation IDs |
| U1–U3 | EN/JA awaiting, confirmed, expired and cancelled browser journeys use the real test backend and manual GET refresh |
| U4–U6 | Moving browser time does not expire the payment; language change makes no request; reload restores reference and delayed outcome without POST |
| U7 | Failed refresh preserves evidence, warns it may be stale, and recovers on another check |
| U8 | 390x844 EN/JA browser checks plus 1280x800 visual review; keyboard Enter and disabled controls verified in the exploratory session |
| U9 | New test hides/clears old evidence; all 11 earlier browser scenarios remain in the expanded suite |

Automated report evidence is in `tests/integration/test_confirmation_reporting.py`.
Browser scenarios are in `features/checkout/async-checkout.feature`. The test-only
backend control exists only in `features/support/test_server.py`; production
application routes do not expose it. Signing secrets are not put in browser code.

## Exploratory execution

Agent-led, scripted interaction plus visual inspection; not a claim of human
usability testing or native Japanese review. Environment: macOS, local Chromium,
isolated temporary SQLite database, synthetic order `explore-日本語-001`.
Viewports: 390x844 and 1280x800. No shared developer database was modified.

1. Create a delayed payment in each language. Observe reference, amount and
   Japan-time deadline. Check that the view says waiting, not declined.
2. Focus refresh and press Enter. Hold a subsequent GET open: refresh and new
   test controls are disabled. Abort it: reference remains and stale warning
   appears. Remove the failure and refresh successfully.
3. Explicitly expire through trusted test setup, then refresh. The view shows
   expiry without saying money was lost. The future displayed deadline in
   these screenshots reflects advancing the backend test clock, not wall time.
4. Inspect mobile wrapping and desktop hierarchy; no horizontal overflow or
   overlapping content observed in retained screenshots. Long references wrap.
5. Automated journeys additionally verify confirmed/cancelled status, reload,
   language change and new-test reset against the live test backend.

Finding E2-EXP-01: the stale warning said “result below” but was positioned below
the result. It was moved above the result, then the EN/JA script was rerun and
the screenshot visually rechecked. Resolved before push.

Retained synthetic evidence:

- [EN awaiting, mobile](evidence/en-awaiting.png).
- [JA expiry, mobile](evidence/ja-expired.png).
- [JA refresh failure after correction](evidence/ja-stale.png).
- [EN expiry, desktop](evidence/en-desktop.png).

Screen-reader use, native Japanese linguistic validation, real-device mobile
testing, and real provider behaviour were not verified. DOM live regions and
keyboard interaction are not substitutes for those checks.

## Local gates

- 397 Python tests passed; branch-aware coverage 85.84%, minimum 85%.
- 49 Node tests and TypeScript check passed.
- 18 Cucumber scenarios, 140 steps passed in Chromium.
- Ruff lint/format and diff checks passed.
- k6 v2.0.0 smoke: traffic/timing, financial verifier, and evidence gates passed.
  Run ID `e2closeout20260914`; generated results under
  `reports/performance/e2closeout20260914/smoke/` (ignored local artifacts).
  The downloaded macOS ARM64 archive matched the pinned release checksum.
  This existing smoke baseline covers synchronous traffic; it is not an
  asynchronous-confirmation load or capacity claim.
- Remote CI will run after the single milestone push; the PR records its result.

## Release recommendation and limits

Ready for the remote CI gate and owner review. Do not merge on local results
alone. All work was kept local until this consolidated milestone delivery.

SQLite serializes writers. Internal diagnostic endpoints lack production
authorization, recovery is explicit rather than unattended, and no provider
integration or real-money safety certification is claimed. Saved confirmation
sections require a new batch to refresh; current source-health checks are not
historical snapshots. Refund restore labels are supported without adding new
refund controls. These are declared scope limits, not hidden unfinished E2 tasks.
