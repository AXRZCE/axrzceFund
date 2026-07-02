# WP3 CP3 — contested mechanics (R4) + PM-01 (R5): readout

**Artifact of record:** `results/wp3_cp3/pm_smoke.json`. Bar authority:
[wp3-done-criteria.md](wp3-done-criteria.md) R4/R5; margin denominator ruled at **R4-PRE**
(`a5592a4` — decision-protocols.md P5.3 now defines `margin = gap / Σ w_i·conviction_i` over all
ballots; the CP2 smoke's three-way divergence recorded as the motivating case; implemented reading
confirmed, no code change).

## R4 — contested mechanics ([graphs/pm.py](../graphs/pm.py) `size_position`, pure code)

`base_size_pct_nav (1.0%) × conviction_factor (0.5–1.5, linear, clipped)` → multiplicative
**downward-only** haircuts (config §5 table: contested ×0.5, regime_mismatch ×0.7,
unresolved_bear_crux ×0.7, liquidity_thin ×0.8 — table guarded against doc drift by
`test_haircut_table_matches_configuration_md`) → hard caps AFTER the haircuts: contested ⇒ ≤0.5%,
DEBATE_FAILED ⇒ ≤0.75%, new position ⇒ ≤2.5%. Phase-1 wiring: `contested` from the tally,
`unresolved_bear_crux` from MOD-01's cruxes; regime/liquidity flags default False until their data
sources land (Macro = Phase 2, liquidity = WP4). Every factor/cap is recorded in a **sizing audit**
so the arithmetic is reproducible from the audit alone.

**Gut demos (restored):** haircut disabled → **3 tests red**; cap disabled → **2 tests red**. The
two contested test cases are designed to separate the guts: conviction 1.0 (cap binds — detects a
gutted cap) and conviction 0.2 (cap silent — detects a gutted haircut). Boundary at exactly 0.20
remains pinned in `test_ballot.py`.

## R5 — PM-01 ([graphs/pm.py](../graphs/pm.py) `run_pm`; **StubPM01 removed**)

- **The model owns judgment, code owns arithmetic** (the TECH-01 pattern): PM-01
  (gemini-3.1-pro/vertex, runtime-scoped) supplies direction/conviction/thesis/stop/invalidation/
  horizon/edge; `size_pct_nav` is **server-authoritative** — computed by `size_position` and
  written over anything the model says.
- **Grounding:** the proposal's attached `ballot_summary` must equal the computed tally
  (`check_ballot_grounding` — a canned PM decision fails). **Override guard** (P6.3/§5.1): against
  the ballot direction requires a written rebuttal; `max_overrides_per_month = 2` enforced;
  `pm_override` events are the durable tally.
- **Edge check:** `expected_edge_bps ≥ 3 × round-trip cost`. ⚠️ **Flagged placeholder:** cost =
  `ASSUMED_ROUND_TRIP_COST_BPS = 20` until the backtesting-framework cost model lands (WP4) — the
  check is real, its second input is a documented stand-in.
- **Replay (R5):** the decision is stored in the event log (`proposal_written`/`no_trade` +
  stamp incl. `manifest_version`); `reconstruct_decision(event_log, cycle_id)` reads it back —
  **structurally client-free** (signature-pinned by test). The manifest-swap identity red test
  (CP0, `tests/test_replay.py`) still stands.
- **Deep-loop:** the `pm` node takes an injected implementation (fail-closed un-wired), same
  pattern as the debate node; tests inject `fake_pm_impl`.

Red tests: `tests/test_pm.py` (14) — contested×2 (gut-separating), non-contested, DEBATE_FAILED,
crux haircut, stacking, conviction clipping, edge boundary, override (no-rebuttal / valid / cap),
canned-PM grounding, replay-no-LLM. Suite: **224 passed**.

## E2E smoke (paid) — `wp3_cp1_20260625` / MDT (different day + sector than CP2's)

Full cycle: memo → VERIF-01 → 3-family debate → sealed votes → tally → **PM-01 real call**:

- Ballot: long 1.30 vs short 0.62, `margin = 0.3542`, **not contested**; dissent = "BEAR-01 voted
  short (0.62)".
- **PM-01 decision:** `trade`, **long with the ballot** (no override), conviction 0.55 →
  factor 1.05 → base 1.05% → **unresolved_bear_crux ×0.7 fired** (MOD left real cruxes) →
  **`size_pct_nav = 0.735%`**, no caps binding. The P6 anchor working as designed: *"when the
  Bear's crux is unresolved, size like it."* Sizing audit embedded in the artifact.
- **Replay check:** `reconstruct_decision` == the stored proposal, event-log only.
- **Synthetic contested demo (code path, zero LLM):** constructed votes → margin 0.10 < 0.20 ⇒
  contested ⇒ conviction 0.9 (factor 1.4 → 1.4%) × **haircut 0.5 → 0.70%** → **cap → 0.50%**. Both
  R4 mechanics fired on the real plumbing.
- Stamps: memo + 7 debate + 3 votes + PM, all carrying `manifest_version`. Vendor scan clean.

## Spend (honest ledger)

| Item | USD |
|---|---|
| CP3 smoke (first attempt succeeded) | **$0.2450** |
| **Cumulative WP3 ledger** | **~$3.575** |

## Next (gated — not started)

CP4 (R6 VERIF-01-as-judge + R7 shadow-ensemble + WP3 readout → PR) begins only after reviewer
verification. No judge code, no shadow code yet.
