# implementation-plan.md — Phased Roadmap from Empty Repo to Full Multi-Agent Fund

**Status:** v1.0 — Foundation document
**Depends on:** all prior docs (this plan sequences their builds)
**Feeds into:** validation-criteria.md (exit gates referenced here get precise numbers there), Claude Code work breakdown

**Planning principles:**
- **Gates, not dates.** Durations below are working estimates for a solo builder using Claude Code; what advances a phase is its exit gate, never the calendar. The one exception: E1 evidence gates have *minimum* calendar time by definition (you cannot rush forward paper trading).
- **The harness comes before the fund.** Phase 0 builds the things that keep us honest; nothing that can self-deceive is built before the machinery that catches it.
- **Every phase ends with a live system.** No phase delivers a pile of parts; each delivers a smaller fund that runs end-to-end every day.
- **Pivot thresholds are pre-committed** (§Phase-gates-and-pivots, from research.md): we decide *now* what evidence would change the design, so the decision later is reading a dashboard, not relitigating hope.

---

## Phase 0 — Foundations & Validation Harness (est. 2–4 weeks)

**Objective:** stand up the data spine, event log, and validation machinery — and prove the machinery catches fraud.

**Workstreams:**
1. **Repo & scaffolding:** monorepo layout (`/core` enforcement library, `/agents`, `/graphs`, `/data`, `/harness`, `/ops`); config loader that hashes configuration.md into `config_version`; structured logging; the replay-tuple stamping utilities (architecture §7.3).
2. **Data spine (api-data-sources.md):** Alpaca paper account + data adapter; Sharadar procurement + `FundamentalsInterface` with mandatory `as_known_at`; EDGAR mirror for a pilot sector; PIT store (DuckDB/Parquet) with `as_of`/`available_at` enforcement; universe service from Sharadar SP500 history; nightly ingestion jobs with staleness sentinels.
3. **Event log:** append-only store, hash chain, the nightly look-ahead audit query (no record read with `available_at > decision_ts` — run it from day one even with no agents yet).
4. **Validation harness (backtesting-framework.md):** Trial Registry (the no-unregistered-backtests API), CPCV engine with purging/embargo, DSR/PSR/PBO/MinTRL calculators, cost model v1, evidence-class labeling in all report outputs.
5. **Broker layer:** `BrokerInterface` + Alpaca adapter + order manager skeleton + fill-divergence logging.

**Exit gate (Phase 0 → 1):**
- **G0.1 Fraud-catch test:** harness run on a deliberately overfit synthetic strategy (fit on full sample) reports it as overfit (PBO high, DSR insignificant); run on a known-good synthetic edge passes. The harness must demonstrably *fail bad strategies* before we trust it to pass good ones.
- **G0.2 PIT proof:** an attempted look-ahead read (test fixture) is refused by the store and caught by the audit query.
- **G0.3 Pipeline soak:** 5 consecutive nightly ingestion runs complete with reconciled row counts; replay of a sampled day rebuilds identical derived tables.

---

## Phase 1 — MVP Debate Pipeline (est. 4–6 weeks build, then ≥3 months E1 accumulation)

**Objective:** the smallest honest fund: one sector, daily deep loop, 8-agent roster, full learning loop, live on paper.

**Scope IN:** FUND-TECH, TECH-01, SENT-01, BULL-01, BEAR-01, MOD-01, PM-01, PMORT-01 + VERIF-01 service (agent-specifications §7); protocols P1–P7 (gate-only risk: no RISKA), P9, P10, P12; episodic memory + probation queue + believability *recording* (memory-systems §8); long-only or long + ETF hedge; simple execution (market-on-open / limit, no EXEC-01); breakers active (whole book = one pod).
**Scope OUT (deliberately):** believability weighting (recording only), intraday escalation mini-graph (monitors + stops only), QUANT-01 (registry has no admitted signals yet — run the first admission in parallel), MACRO-01, multi-sector, shorts beyond hedges, META-01.

**Build sequence:**
1. LangGraph deep-loop skeleton with stub agents (returns canned memos) → end-to-end state machine + checkpointing proven before any real LLM spend.
2. Real agents one at a time against golden-day fixtures (recorded historical days post-cutoff): schema conformance, verifier strip behavior, budget metering.
3. Debate + ballot + PM nodes; conformity-event logging live from the first debate.
4. Risk gate + order manager + intraday monitor loop (stops/invalidation/breakers).
5. P9 learning loop + consolidation job; dashboard v1 (P&L, exposures, costs, MinTRL countdown, fill divergence).
6. **Dry-run week:** full daily cycles, orders logged but not submitted; human reviews every decision record for protocol fidelity.
7. Go live on paper; begin the E1 clock.

**Standing experiment from day one:** every cycle also computes the **independent-ensemble shadow decision** (votes straight from P2 memos, no debate) — logged, not traded. This accumulates the debate-vs-ensemble comparison (backtesting-framework §7) for free.

**Exit gate (Phase 1 → 2):** precise numbers in validation-criteria.md; shape of the gate:
- **G1.1 Operational:** ≥60 consecutive trading days with zero unexplained halts, look-ahead audit clean, reconciliation clean.
- **G1.2 Protocol quality:** memo strip rate, role-violation rate, conformity-event rate all below thresholds; cost per decision within budget.
- **G1.3 Evidence:** ≥3 months E1, ≥40 closed trades; performance evaluated vs. both benchmarks with PSR reported — *the gate at this stage is "the machine works and the record is interpretable," not "alpha is proven"* (MinTRL math says 3 months cannot prove alpha; pretending otherwise would violate our own framework).
- **G1.4 Learning loop:** ≥1 lesson promoted through full probation pipeline; believability records populating correctly per version tuple.

---

## Phase 2 — Pods, Risk Depth, Signal Registry (est. 6–8 weeks build, overlapping continued E1)

**Objective:** the organizational fund: multi-sector pods, governance agents, admitted quant signals, honest execution.

**Scope IN:** remaining FUND-{sector} agents as pods with per-pod breakers; MACRO-01; RISKA-01 + COMP-01 ahead of the gate; EXEC-01 + slicing; QUANT-01 backed by first registry-admitted signals (run 2–3 classic candidates — e.g., post-earnings drift, 12-1 momentum — through full E2 admission; admit only survivors); intraday escalation mini-graph (P8 complete); shorts (easy-to-borrow); factor model selection + attribution split; no-trade counterfactual episodes; Polygon upgrade when slippage measurement begins; Postgres migration if event volume warrants (ADR-7 trigger).

**Build order rule:** governance before breadth — RISKA/COMP/attribution land *before* sector expansion, so the wider book is never less supervised than the narrow one was.

**Exit gate (Phase 2 → 3):**
- **G2.1:** ≥2 sectors running ≥2 months with pod-level attribution separating cleanly (residual P&L per pod computable).
- **G2.2:** ≥1 registry-admitted signal contributing, with live behavior within its E2 confidence bands (a signal violating its own backtest distribution triggers re-validation, and that trigger has been exercised at least once — deliberately if necessary).
- **G2.3:** cost model recalibrated once against measured fill divergence; edge_to_cost check now uses measured-calibrated costs.
- **G2.4:** escalation mini-graph exercised (real or fire-drill) within timeout; breaker fire-drill passed (synthetic drawdown trips pod halve → verify automatic de-risk end-to-end).
- **G2.5 Evidence:** cumulative ≥6 months E1 spanning ≥2 regime labels; PSR vs. 0 reported with MinTRL status; *pivot review checkpoint #1 (see below) formally held.*

## Phase 3 — Believability Weighting & Meta-Agent (est. 4–6 weeks build + experiment time)

**Objective:** the self-improving fund: track records start steering, process evolution begins — both under experimental control.

**Scope IN:** P5 weighting A/B (candidates randomized equal-vs-weighted once ≥25 scored calls per agent per domain accumulate); META-01 live with human approval queue + first measured change experiments (P11); conformal-gated sizing pilot (research.md Tier 1) as a registered experiment; net-band tightening per configuration §6 target; Russell 1000 expansion *decision* (not default).

**Exit gate (Phase 3 → 4):**
- **G3.1:** weighting experiment reaches its pre-registered sample size; weighted arm ≥ equal arm on decision-quality metric → weighting stays on; otherwise it stays off and that result is *fine* (the experiment, not the feature, was the deliverable).
- **G3.2:** ≥3 META-01 changes deployed and measured against their own expected_effect; ≥1 rollback exercised cleanly.
- **G3.3:** debate-vs-ensemble shadow comparison (running since Phase 1) formally read out → debate gate (P3 thresholds) re-tuned or debate scope reduced per evidence.

## Phase 4 — Full Fund & Capacity Review (ongoing)

**Scope IN:** alt-data analyst if a concrete source justifies it; tail-hedge overlay study (deep hedging — only with options data procurement and its own E2-grade validation); capacity analysis (at what NAV would modeled impact erode the edge?); full attribution dashboards; the standing quarterly Validation Report as the operating rhythm.
**Explicitly not a goal:** live capital. That conversation requires MinTRL-satisfying E1 evidence (realistically 18–36+ months) and is out of scope for this plan by design.

---

## Phase Gates and Pivots (pre-committed, from research.md)

**Pivot review checkpoints:** at G2.5 and every 6 months of E1 thereafter, answer from the dashboard:
1. **Is residual (decision) P&L distinguishable from zero after costs?** If after MinTRL-meaningful time the answer is no → **Pivot A:** LLM layer re-scoped from alpha generation to risk/governance/research-synthesis over quant signals (the research.md base case). The architecture survives this pivot intact — that was a design requirement.
2. **Does debate beat the independent-ensemble shadow?** If consistently no → **Pivot B:** P4 demoted to high-stakes-only or replaced by ensemble + single critic pass; cost savings redirected to breadth.
3. **Does weighting beat equal weights?** If no → stays off, permanently fine.
4. **Is any pod persistently below its cost of attention?** → pod archived (its episodic data retained — we halt pods, we don't delete learning).

**Standing risks to this plan (top 4):**
- *Scope creep into Phase 1* — the plan's only defense is the gate list; anything not in Scope IN waits.
- *E1 impatience* — the temptation to "just check" an in-window agent backtest and believe it. E4 watermarking + this sentence are the defense.
- *Solo-builder bus factor* — mitigated by the docs themselves + replayability; the system is its own documentation trail.
- *Model API churn* — version pinning + the abstraction layers (ADR-1/2) + version-tuple believability resets are the absorbers; expect 1–2 forced model migrations during the plan and budget a week each.

## Working Cadence (suggested)
Daily: review yesterday's cycle record (15 min — the decision log is designed to be skimmable). Weekly: cost + protocol-quality dashboard; probation queue. Monthly: fill-divergence and cost-model check. Quarterly: Validation Report + memory review (the two human rituals that keep the machine honest).

## Immediate Next Actions (Phase 0, week 1)
1. Create repo skeleton + config hashing + logging utilities.
2. Open Alpaca paper account; procure Sharadar (single-user, core bundle); verify both APIs with hello-world pulls.
3. Build the PIT store schema + the look-ahead refusal test (G0.2 is achievable in week 1 and sets the tone).
4. Start the Trial Registry — it must exist before the first real backtest is ever run.
