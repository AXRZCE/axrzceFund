# G0 Gate Memo — READY FOR SIGNATURE (Phase 0 → Phase 1)

**Status (2026-06-24): ALL FIVE G0 CRITERIA GREEN.** G0.1 ✅ · G0.2 ✅ · G0.3 ✅ ·
G0.4 ✅ · G0.5 ✅. Each is recorded below against its artifact. Awaiting the project
owner's review and signature — the human gate. **No Phase 1 build until signed.**
**Rule:** validation-criteria.md — ALL criteria must pass; no waivers.

---

## Standing rulings (made before the evidence they govern)

- **Soak window (G0.3):** the raw-archiving refactor changed the ingestion code
  after the first manual run on 2026-06-10. G0.3 must test the pipeline as it will
  actually run, so the five consecutive soak nights count from the first night
  under the refactored (archived) pipeline: **soak window = nights 2–6**, i.e. the
  scheduled 21:30 runs starting 2026-06-10. The earlier same-day manual runs are
  baseline/shakedown, not soak evidence.
- **G0.4 replay target:** night 2 or later (night-1 runs predate raw archiving).
- **Soak host (2026-06-15, after the laptop failure):** the soak runs on the
  always-on VM (DigitalOcean, Ubuntu 24.04) via **systemd timers**, isolated under
  `/root/hedgefund` (own venv on system Python 3.12, own `.env`, never touching the
  co-resident ANTS project). The laptop is decommissioned as a soak host. The five
  consecutive clean nights count the `21:30 ET` (`hedgefund-soak.timer`) firings
  starting after the timer-fired mechanism proof lands clean.
- **Catch-up-night counting (pre-committed 2026-06-15, before it can occur):** the
  soak timer uses `Persistent=true`, so if the VM is down/restarting at 21:30 ET the
  run fires on next boot rather than being missed. **A catch-up run that completes
  cleanly (all_ok, PIT audit clean, reconciliation passed) COUNTS as a clean soak
  night** — the pipeline ran, the data landed, operational reliability was
  demonstrated; only the wall-clock time shifted. This is the sensible standard, and
  strictly better than the laptop's all-or-nothing. A catch-up run that fails its
  checks does NOT count and restarts the 5-night counter, same as any failed night.
- **Timeout-killed-run counting (pre-committed 2026-06-15, before it can occur):**
  the soak/G0.5 services carry `TimeoutStartSec=1800`, so a hung run (e.g. a network
  stall mid-fetch) is killed at 30 min rather than blocking the next night's timer.
  **A run killed at the timeout is an operational failure: it does NOT count as a
  clean night and the 5-night counter does not advance** (holds, then restarts on the
  next outcome). Honest reading — a killed run did not demonstrate clean operation.
- **Seed bookkeeping (G0.1):** {0..19} consumed (v1 + effective-N diagnosis);
  {20..39} consumed (v2 run under original thresholds); **{40..59} = the final
  gate ensemble.** Pre-committed: a failure on {40..59} triggers full stop and
  first-principles joint review — no third threshold iteration.

## G0.1 — Fraud-catch (criteria as finally restated; see amendment log)

History (this narrative is part of the evidence the gate was honest):
1. Single-run gate → restated as 20-seed ensemble (pre-committed before running).
2. v1 campaign: effective N = 6.8/208 (mirrored families, reused seeds). Diagnosed
   via eigenvalue effective-N per the pre-committed decision tree; redesigned with
   a-priori target effN ≥ 60; intermediate random-linear design hit the lag-space
   dimensionality ceiling (13.5); final design (independent junk-indicator
   channels) verified effN ≈ 100 BEFORE any PBO was computed.
3. v2 run on fresh seeds {20..39}: both original thresholds shown to encode
   impossible demands (PBO ≥ 0.60 requires anti-persistence iid noise cannot
   produce — uniform-rank symmetry centers noise PBO at 0.5; 20/20 positive seeds
   at IC=0.04/10y demanded ~100% power where honest power is ~80%). Detector
   contrast decisive: neg 0.514 vs pos 0.028. Stopped per decision tree; owner
   restated both arms (final restatement, amendment log 2026-06-10 (final)).
4. Final run on seeds {40..59}: **PASSED 2026-06-10** — artifact:
   docs/g01-readout-final-seeds40-59.json (no re-runs per decision tree Outcome 1).

- [x] **G0.1a (contrast):** neg median PBO **0.456** ≥ 0.45 (squarely in the
      no-skill band theory predicts), neg median DSR p **0.541** ≥ 0.20, neg
      median |IC| **0.0025** ≤ 0.01, pos median PBO **0.000** < 0.25 — PASS
- [x] **G0.1b (positive, 20y panel):** DSR p < 0.05 in **20/20** seeds (≥ 19
      required; worst seed p = 0.038), median p **1.5e-05** < 0.01; realized IC
      0.0403 vs 0.04 target; true `factor` family selected in all 20 seeds — PASS

## G0.2 — PIT refusal

- [x] **G0.2a (read filter):** mixed-age store query returns only knowable rows,
      never throws — tests/test_pit_store.py::TestReadFilter (6 tests)
- [x] **G0.2b (audit):** audit_future_data() fires on future-stamped rows —
      tests/test_pit_store.py::TestAuditFutureData (5 tests)
- Three-layer design documented (architecture.md §L1); canonical-UTC invariant
  enforced and regression-tested (mixed-offset bug caught and fixed).

## G0.3 — Ingestion soak — PASSED (5 of 5 clean; held clean through night 9, 2026-06-24)

- [x] **5 consecutive clean nightly runs**, VM systemd timer 21:30 ET, every run
      `all_ok` + PIT 0; the single row-count deviation is **explained** (below).
      Night 1 = first `hedgefund-soak.timer` firing, 2026-06-16 21:30 ET. Every
      night fired on-schedule at 01:30 UTC (no missed nights, no catch-up runs, no
      timeout-kills). Night-by-night:

  | Night | Date (21:30 ET) | summary file | all_ok | PIT | IEX | recon |
  |---|---|---|---|---|---|---|
  | 1 | 2026-06-16 | night_…0617T014037Z | ✅ | 0 | 2515 | `[]` |
  | 2 | 2026-06-17 | night_…0618T014244Z | ✅ | 0 | 2515 | `[]` |
  | 3 | 2026-06-18 | night_…0619T014047Z | ✅ | 0 | 2520 | `[]` |
  | 4 | 2026-06-19 | night_…0620T013915Z | ✅ | 0 | 2016 | `[]` |
  | 5 | 2026-06-20 | night_…0621T013930Z | ✅ | 0 | 2016 | `[]` |
  | 6–9 | 06-21 … 06-24 | (continued) | ✅ | 0 | 2016 | `[]` |

- **Row-count deviation — EXPLAINED (logged per G0.3 "explained = logged"):** IEX
  daily-bar counts moved 2515 → 2520 → 2016 across the window. **This is a
  market-calendar effect, not a coverage loss.** IEX rows = (universe names) ×
  (trading days in the trailing 7-calendar-day window). Verified 2026-06-24:
  `get_universe` = **504**, and every recent trading date carries the full ~503–506
  tickers — so 504 × 5 days = 2520, 504 × 4 days = 2016. The drop to 4 trading days
  is the **June 19 Juneteenth market holiday** (plus weekend positioning) shrinking
  the lookback's trading-day count. Universe coverage is intact; only the window's
  day count changed. (The 50% reconciliation tolerance did not auto-flag the 20%
  move; per the G0.3 ruling it is the nightly human review — performed here — that
  adjudicates, and it is clean.)
- **Canonical host PROVEN 2026-06-15 (the saga's close):** ported to the always-on VM
  (Ubuntu 24.04, systemd timers, isolated `/root/hedgefund`). Stand-up evidence:
  data layer verified (Sharadar 5/5, Alpaca ACTIVE); first run `all_ok`, universe 503,
  IEX 2515; **timer-fired proof** — `hedgefund-soak.timer` triggered `hedgefund-soak.service`
  (journal `02:59:11 Starting…`, not a manual invocation), `.env` loaded under
  systemd's bare environment, ran 15 min to clean completion (run `ingest_20260616_f63c9e`,
  `all_ok`, PIT 0, IEX 2515, **reconciliation [] clean** `2515→2515`). systemd
  `Persistent=true` (reboot catch-up) + `TimeoutStartSec=1800` (hung-run self-heal).
- **INCIDENT 2026-06-10 → 06-15: the first soak attempt produced ZERO clean nights.**
  Per the pre-committed "missed night restarts the count" rule, the count is reset.
  Root causes (both in the scheduling layer; pipeline code was healthy throughout):
  1. **`.cmd` wrapper redirect bug.** Log filename used `%date%` substitution which,
     under the machine's dd/MM/yyyy locale, produced an invalid path (contained `/`).
     cmd aborted the redirect *before launching python*, so every scheduled run
     (nightly catch-ups + the 06-11 G0.5) executed the wrapper but never ran python.
     Evidence: `var/g05` created (mkdir ran) but empty; zero console logs anywhere.
     Fixed: both wrappers now use a fixed, locale-independent filename (console_soak.log).
  2. **Never-sleep power setting reverted** to 30-min (a Windows-update reboot switched
     the active power scheme to "Performance", discarding the 06-10 setting on the
     prior scheme). Modern Standby can't timer-wake, so the laptop slept through every
     21:30. Re-applied on the active scheme; StartWhenAvailable catch-up is the real
     safety net (one run on next wake).
  3. **Verification gap (the lesson):** on 06-10 the *wake test* used a simple wrapper
     with no date-redirect, so the real wrappers' redirect bug was never exercised
     before going live. Fix verified end-to-end this time by running the actual task.
- **Bug surfaced by soak reconciliation (the soak doing its job), now fixed:**
  SP500 universe `available_at` was stamped `now()` for all historical constituent
  rows → `get_universe` resolved on an arbitrary tie-break among equal timestamps →
  empty universe → IEX coverage collapsed 2515→10 rows (10-name fallback). Fixed:
  `transform_sp500` stamps `available_at` = the change date (native knowledge time);
  verified get_universe NOW = 503 names, deterministic. (Historical PIT membership
  is incomplete — Sharadar lacks a pre-coverage baseline — tracked as a Phase 1 item;
  not a G0 blocker since the soak/IEX only needs the current universe.)
- Night-by-night log table: to be filled from var/ingestion_logs/ once the restarted
  soak runs.
- Findings banked from shakedown (both doc'd in api-data-sources): SF1 `as_of` =
  reportperiod; corporate-actions announcement semantics (available_at < as_of valid).

## G0.4 — Replay determinism

- [x] **PASS on the canonical VM host** against the timer-fired soak archive
      `ingest_20260616_f63c9e` (a genuine systemd-triggered run): all archives
      SHA256-verified; all 4 tables byte-identical — price_bars 33,695
      (ae5438e11a3e), fundamentals 43,119 (ea58fbd295d5), universe_membership
      59,116 (e6ecf2b005bd), corporate_actions 5,334 (e505ab0d9f79). Artifact:
      `var/g04/replay_ingest_20260616_f63c9e.json` on the VM.
- Mechanism additionally verified twice on the laptop (2026-06-10 shakedown archive
  and 2026-06-15 archive), both byte-identical — determinism is robust across hosts.

## G0.5 — Broker round-trip

- [x] **PASS** — fired from the VM (`hedgefund-g05.timer`) 2026-06-16 10:00 ET
      (14:00 UTC), market hours: **10 orders, zero mismatches, modeled-fill logged
      on all 10**, account flat after. Artifact: `var/g05/g05_20260616_8b8c4d.json`
      on the VM.

---

**Sign-off (owner, only when all boxes are checked):**

> I have reviewed each criterion against its artifact. G0 is passed; Phase 1 may begin.
>
> Signed: ______________  Date: ______________
