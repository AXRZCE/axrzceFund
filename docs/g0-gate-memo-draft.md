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

## G0.3 — Ingestion soak (nights 2–6)

- [ ] 5 consecutive scheduled nightly runs, zero unexplained row-count deviations
- Night-by-night log: var/ingestion_logs/ (summaries) — table to be filled here.
- Findings already banked from shakedown night 1 (both doc'd in api-data-sources):
  SF1 `as_of` = reportperiod (calendardate is a label that can postdate filing);
  corporate-actions announcement semantics (available_at < as_of valid, table-scoped).

## G0.4 — Replay determinism

- [ ] One sampled soak night (≥ night 2) rebuilt from raw archive byte-identically —
      ops/replay_check.py, artifact: _pending_

## G0.5 — Broker round-trip

- [ ] 10 scripted paper orders submit→fill→reconcile, zero mismatches, modeled-fill
      logged on all 10 — ops/broker_roundtrip.py (market-hours run), artifact: _pending_

---

**Sign-off (owner, only when all boxes are checked):**

> I have reviewed each criterion against its artifact. G0 is passed; Phase 1 may begin.
>
> Signed: ______________  Date: ______________
