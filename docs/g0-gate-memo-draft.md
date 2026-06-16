# G0 Gate Memo — DRAFT (Phase 0 → Phase 1)

**Status:** Draft — accumulating evidence as criteria close. Signed by the project
owner only when every criterion below is green with its artifact linked.
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

## G0.3 — Ingestion soak (RESTARTED — soak window TBD after scheduling decision)

- [ ] 5 consecutive scheduled nightly runs, zero unexplained row-count deviations
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

- [ ] One sampled soak night (≥ night 2) rebuilt from raw archive byte-identically —
      ops/replay_check.py, artifact: _pending official soak-night run_
- Mechanism verified 2026-06-10 against the shakedown-day archive
  (run `ingest_20260610_e9e371`): all 5 archives SHA256-verified; all 4 tables
  byte-identical — price_bars 33,033 rows (be51dfaa5e57), fundamentals 57,083
  (ede79b6dc977), universe_membership 59,116 (2b96cbf8eb58), corporate_actions
  5,139 (ea66f6bae5de). Official evidence run = same drill against a night-2+
  archive per the soak-window ruling.

## G0.5 — Broker round-trip

- [ ] 10 scripted paper orders submit→fill→reconcile, zero mismatches, modeled-fill
      logged on all 10 — ops/broker_roundtrip.py (market-hours run), artifact: _pending_

---

**Sign-off (owner, only when all boxes are checked):**

> I have reviewed each criterion against its artifact. G0 is passed; Phase 1 may begin.
>
> Signed: ______________  Date: ______________
