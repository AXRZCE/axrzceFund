# validation-criteria.md — Precise Phase Gates: The Numbers That Decide

**Status:** v1.0 — Tier 3 document
**Depends on:** implementation-plan.md (gate shapes), backtesting-framework.md (statistics & evidence classes), configuration.md (parameters), monitoring-metrics.md (where each number is read)
**Rule of this document:** every criterion is **falsifiable, machine-checkable where possible, and read off a named dashboard metric**. "It feels ready" appears nowhere. Where judgment is unavoidable, the criterion names the judge and the written artifact the judgment must produce.

**Conventions:** each gate lists criteria as `[ID] metric — threshold — source panel — verdict type (AUTO = computed; HUMAN = signed memo required)`. ALL criteria must pass; a gate may not be waived, only amended via P11 with written rationale *before* the evaluation, never during it (no moving goalposts mid-test).

---

## G0 — Phase 0 → Phase 1 (the harness is trustworthy)

- **[G0.1a] Fraud-catch, contrast criterion** — over the pre-committed seed ensemble **{40..59}**: negative-control **median PBO ≥ 0.45** (the no-skill band: for genuinely independent noise trials the IS-best's OOS rank is uniform by symmetry, so PBO centers at 0.5 — that IS the fully-overfit verdict in Bailey et al.'s framing; values above 0.5 require anti-persistence iid noise cannot produce) **AND negative median DSR p ≥ 0.20 AND negative median |realized IC| ≤ 0.01 AND positive-control median PBO < 0.25**. The gate tests what the statistic actually measures: the detector must *separate* the two worlds; the positive threshold doubles as the Phase-2 admission bar doing its real job — harness report — AUTO
- **[G0.1b] Fraud-catch, positive control** — planted true edge (injected IC ≈ 0.04 — the realism anchor, untouched), synthetic panel extended to **20 years** (T is a free parameter of a synthetic world; at T=20y a true SR≈1 edge has t ≈ 4.5 pre-deflation): **DSR p < 0.05 in ≥ 19 of 20 seeds AND median p < 0.01** at the true trial count. The 19/20 allowance acknowledges even strong power isn't a per-seed guarantee; the median condition prevents a cluster of marginal passes — harness report — AUTO
  > Both criteria are **distributional over a fixed, a-priori seed set**, never a single run. Seeds {0..39} are consumed diagnosis data (twice over) and may never be reused for gating. **Pre-commitment: this is the final restatement.** If the gate fails on these criteria, the response is a full stop and joint review of the harness from first principles — not a third iteration of thresholds. Two restatements with documented reasoning is science; a third without a stop is threshold-shopping.
- **[G0.2] PIT refusal** — test-fixture read with `available_at > decision_ts` is refused by the store AND caught by the nightly audit query — D6 look-ahead audit — AUTO
- **[G0.3] Ingestion soak** — 5 consecutive nightly runs, zero unexplained row-count deviations (explained = logged vendor revision) — D6 freshness — AUTO
  > **Host & counting (pre-committed 2026-06-15, see g0-gate-memo-draft.md):** the soak runs on the always-on VM via systemd timers (`hedgefund-soak.timer`, 21:30 ET), isolated under `/root/hedgefund` (not the laptop). Two counting rulings, fixed before they could occur: (a) a `Persistent=true` **catch-up run** that fires on next boot and completes cleanly **COUNTS** as a clean night (only wall-clock shifted); (b) a run **killed at `TimeoutStartSec=1800`** is an operational failure that does **NOT** count and the 5-night counter holds/restarts.
  > **What "zero unexplained deviations" actually gates:** the nightly `all_ok` exit covers job success + PIT audit ONLY. `reconciliation_flags` (night-over-night row counts; 50% per-job tolerance, first night = baseline auto-pass, compared against the immediately previous night) and `staleness` are **advisory signals surfaced for human adjudication — they do NOT auto-fail the run.** G0.3 is enforced by **human review** of those fields each night, not by the exit code. Do not "fix" reconciliation/staleness into the `all_ok` gate, and do not assume `all_ok` already covers them.
- **[G0.4] Replay determinism** — one sampled day's derived tables rebuilt from raw archive byte-identical (hash match) — rebuild drill — AUTO
- **[G0.5] Broker round-trip** — 10 scripted paper orders: submit → fill → reconcile with zero recon mismatches; modeled-fill logging populated on all 10 — D6 reconciliation — AUTO

## G1 — Phase 1 → Phase 2 (the machine works; the record is interpretable)

**Operational (60-trading-day window, contiguous):**
- **[G1.1a] Cycle reliability** — ≥ 98% of scheduled deep-loop cycles completed without human rescue (≤1 failure-with-intervention per 60) — D6 heartbeats — AUTO
- **[G1.1b] Look-ahead audit** — zero hits, entire window — D6 — AUTO (this criterion repeats at every gate; it is never not a criterion)
- **[G1.1c] Reconciliation** — zero unresolved mismatches; any exit-only episodes resolved ≤ 2 cycles — D6 — AUTO
- **[G1.1d] Halt hygiene** — every halt/no-trade event has a logged cause; zero "unknown" causes — event log query — AUTO

**Protocol quality (same window):**
- **[G1.2a] Memo discipline** — fund-wide strip rate ≤ 15%; no single agent > 25% sustained (4-week roll) — D2 strip rate — AUTO
- **[G1.2b] Role integrity** — ≤ 2 debate role violations total; zero in final 30 days — D3 — AUTO
- **[G1.2c] Conformity** — no agent over conformity_flag_threshold (3 unexplained flips / 20 ballots) in the window — D3 — AUTO
- **[G1.2d] Cost discipline** — cost per decision ≤ $8 at p90; ≤ 10 degrade engagements in window; daily budget never silently exceeded (degrades are visible events) — D4 — AUTO
- **[G1.2e] Schema robustness** — node failure rate from unparseable outputs ≤ 2% of LLM calls — D6 node failures — AUTO

**Evidence & learning:**
- **[G1.3a] Sample** — ≥ 3 months E1 elapsed AND ≥ 40 closed trades — D1 — AUTO
- **[G1.3b] Interpretability, not alpha** — PSR vs 0 and vs SPY computed and rendered with MinTRL status; attribution v0 (beta + sector via ETF proxy) separates residual P&L — D1 — AUTO. **Explicit non-criterion:** no return or Sharpe threshold at G1. Demanding "alpha" from a 40-trade record would violate backtesting-framework §4; a positive-return requirement here would select for luck and teach the project to chase noise. What IS required: the record renders honestly and nothing in it is *uninterpretable*.
- **[G1.3c] Catastrophe screen** — max drawdown did not trip fund_halt (−10%); if pod_halve (−5%) tripped, the automatic response executed to spec — D1 breakers — AUTO
- **[G1.4a] Learning loop live** — ≥ 1 lesson promoted through full probation (3 independent confirmations); ≥ 1 demotion or contradiction logged (the falsifiability machinery demonstrably bites) — D5 funnel — AUTO
- **[G1.4b] Believability recording** — scored-forecast records accruing for 100% of memos and ballots, correctly keyed by version tuple (sampled audit, n=20) — D5 — HUMAN (signed audit memo)
- **[G1.5] Shadow ensemble integrity** — independent-ensemble shadow decision logged for 100% of decided candidates (the G3.3 experiment's data is accumulating cleanly) — D3 — AUTO

## G2 — Phase 2 → Phase 3 (the organization scales without losing supervision)

- **[G2.1a] Pod separation** — ≥ 2 sector pods live ≥ 2 months each; per-pod residual P&L computable with factor model attribution (factor model selected and documented) — D1 residual — AUTO + HUMAN (model-selection memo)
- **[G2.1b] Governance precedence** — RISKA-01 + COMP-01 live before second pod activated (verified from event-log timestamps — the "governance before breadth" rule is checkable, so check it) — event log — AUTO
- **[G2.2a] Signal admission** — ≥ 1 signal through full E2 admission (CPCV + DSR p<0.05 at true N + PBO<25% + survives 2× costs + rationale memo) — Trial Registry — AUTO + HUMAN (rationale)
- **[G2.2b] Live-vs-backtest fidelity** — admitted signal's live E1 behavior within its CPCV path distribution (no KS-test rejection at 5%); the re-validation trigger exercised ≥ once — registry + D1 — AUTO
- **[G2.3] Cost-model recalibration** — one full recalibration completed against ≥ 200 measured fills; updated ⟨impact_coeff⟩ documented; edge_to_cost check switched to calibrated model — fill-divergence report — AUTO + HUMAN
- **[G2.4a] Escalation drill** — P8 mini-graph completed within 10-min timeout on a real or synthetic event; default-derisk fallback tested separately — drill log — AUTO
- **[G2.4b] Breaker fire-drill** — synthetic pod drawdown trips halve → automatic de-risk verified end-to-end (orders generated, exposures halved, events logged) — drill log — AUTO
- **[G2.5a] Evidence accumulation** — cumulative ≥ 6 months E1 spanning ≥ 2 distinct MACRO regime labels — D1 — AUTO
- **[G2.5b] Pivot review #1 held** — the four pivot questions (implementation-plan) answered in a signed memo from dashboard data; any triggered pivot enacted or explicitly scheduled — HUMAN

## G3 — Phase 3 → Phase 4 (self-improvement is evidence-based)

- **[G3.1a] Weighting experiment complete** — pre-registered decision-quality metric and sample size reached (registered in Trial Registry before arm assignment begins); weighted vs equal arms compared per the registration — registry — AUTO
- **[G3.1b] Weighting verdict enacted** — weighted ≥ equal on the registered metric → ON stays; else OFF stays. Either outcome passes; an unregistered or post-hoc-modified comparison fails the gate — HUMAN (verdict memo)
- **[G3.2a] META-01 throughput** — ≥ 3 change proposals deployed with measured outcomes vs their own expected_effect at the 4-week horizon; ≥ 2 of 3 within predicted direction — P11 records — AUTO
- **[G3.2b] Rollback exercised** — ≥ 1 clean rollback executed (real or drill) — P11 records — AUTO
- **[G3.3] Debate readout** — debate-vs-ensemble shadow comparison formally analyzed (pre-registered metric, ≥ 9 months of paired data); P3/P4 re-tuned or debate scope reduced per the result; verdict memo signed — registry + D3 — HUMAN
- **[G3.4] Standing integrity** — G1.1b (look-ahead zero), G1.2c (conformity), G1.1c (reconciliation) all still clean over the Phase 3 window — D3/D6 — AUTO

## G4 / Steady State — the quarterly bar (no graduation, only maintenance)

Every quarter, the Validation Report must show: look-ahead zero; reconciliation clean; all active signals within live-vs-backtest fidelity bands (else re-validation triggered); lesson review completed; cost within budget trend; pivot questions re-answered once ≥ 12 months E1. **Live-capital discussions** (out of scope, but the bar pre-committed): PSR ≥ 95% vs 0 on residual P&L, track record ≥ MinTRL for SR* = 0.5 at observed moments, across ≥ 3 regime labels — realistically 18–36 months away, and that is the honest answer.

## Quantified Pivot Triggers (pre-committed numbers for implementation-plan's pivots)

- **Pivot A (LLM layer → governance-only):** at any pivot review with ≥ 12 months E1: residual P&L PSR vs 0 < 60% AND upper 90% bootstrap CI on residual SR < 0.5 → enact Pivot A. (Below MinTRL, the review may *defer*, never *conclude success*.)
- **Pivot B (demote debate):** G3.3 readout shows ensemble arm ≥ debate arm on the registered metric with ≥ 80% bootstrap confidence → debate becomes high-stakes-only (P3 thresholds tightened to top size-decile candidates).
- **Pivot C (weighting off):** per G3.1b, symmetric.
- **Pod archive:** pod residual P&L negative AND below pod cost-of-attention (LLM $ + data $) for 2 consecutive quarters → archive (halt, retain episodes).

## Amendment Log
| Date | Gate | Change | Rationale | Approved by |
|---|---|---|---|---|
| 2026-06-10 | G0.1a / G0.1b | Restated as distributional criteria over a pre-committed seed ensemble {0..19}: G0.1a → median PBO ≥ 0.60 AND PBO > 0.50 in ≥ 80% of seeds AND median DSR p ≥ 0.20; G0.1b → DSR p < 0.05 in every one of the 20 seeds. Negative control broadened to a multi-family research campaign. | Single-run PBO has high sampling variance under correlated trials; a single-seed gate would let the seed be selected with knowledge of the outcome (backtest tuning applied to the validator). Ensemble criterion eliminates seed selection. Amended before the gate test was run, never during. | User (project owner), 2026-06-10 |
| 2026-06-10 (final) | G0.1a / G0.1b | **Final restatement** (recorded before the {40..59} run): G0.1a → contrast criterion (neg median PBO ≥ 0.45 in the no-skill band, neg median DSR p ≥ 0.20, neg median \|IC\| ≤ 0.01, pos median PBO < 0.25); G0.1b → positive panel extended to 20 years at IC=0.04 unchanged, DSR p < 0.05 in ≥ 19/20 seeds AND median p < 0.01. Fresh seeds {40..59}; {0..39} consumed. **Pre-commitment: if this fails, full stop and first-principles joint review — no third threshold iteration.** | The v2 readout (seeds {20..39}, effective N ≈ 100 verified a priori) showed both original thresholds encoded impossible demands: PBO ≥ 0.60 required anti-persistence iid noise cannot produce (IS-best's OOS rank is uniform by symmetry → PBO centers at 0.5, which IS the overfit verdict per Bailey et al.); 20/20 positive seeds at IC=0.04/10y/209 trials demanded ~100% power where the honest figure is ~80% (4 misses all had panel IC at the low sampling tail; diagnostics exonerated the harness). Detector contrast was decisive: neg 0.514 vs pos 0.028. | User (project owner), 2026-06-10 |
| 2026-06-10 (later) | G0.1 negative-control design | Campaign v1 (208 trials, effective N ≈ 6.8 by eigenvalue diagnosis — reversal was momentum's exact negation; random family reused 4 seeds with shared draws) redesigned to campaign v2: 209 trials = non-mirrored sparse deterministic families + 170 junk-indicator trials, each an independent noise data channel (unique seed). An intermediate attempt with unique-seed random-LINEAR features only reached effective N ≈ 13.5 — returns-based linear features live in lag-space of dimension ≤ max lookback (10), a hard ceiling; independent indicator channels remove it. **A-priori design target: effective N ≥ 60, verified by construction BEFORE any PBO is computed on the redesigned campaign.** Gate re-runs on fresh pre-committed seeds **{20..39}**; seeds {0..19} are consumed as diagnosis data and may never be reused for gating. | Per the pre-committed decision tree (docs/g01-decision-tree.md, Outcome 2): PBO ≈ 0.5 under effective-N ≈ 7 is the statistic answering truthfully — the control wasn't presenting enough genuine selection to detect. Redesign makes the control representative of a real multi-source data-mining campaign; fresh seeds prevent fitting the control to the diagnosis data. Thresholds unchanged. Recorded before the v2 gate run. | User (project owner) via decision tree, 2026-06-10 |
