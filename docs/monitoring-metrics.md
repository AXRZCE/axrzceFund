# monitoring-metrics.md — KPIs, Dashboards, and Alerts: The Fund's Instrument Panel

**Status:** v1.0 — Tier 3 document
**Depends on:** decision-protocols.md (every protocol emits metrics), configuration.md (thresholds), backtesting-framework.md (evidence classes, statistics), memory-systems.md (memory health)
**Feeds into:** the daily/weekly/quarterly review cadence (implementation-plan.md), META-01's process mining inputs

**Design principles:**
1. **Every metric has an owner-question.** A metric nobody would act on is noise; each entry below names the question it answers and the action its breach triggers.
2. **Process metrics outrank outcome metrics early.** For the first MinTRL-deficient year, P&L is mostly noise; protocol fidelity, calibration, and cost discipline are signal. Dashboard layout reflects this priority.
3. **Honest rendering rules.** Performance numbers render with their evidence class, uncertainty intervals, and MinTRL status, or they render greyed-out (backtesting-framework §8). The dashboard is contractually incapable of showing a naked Sharpe.

---

## Dashboard 1 — Fund Performance & Risk (the classic panel, with honesty rails)

| Metric | Definition / cadence | Question it answers | Alert / action |
|---|---|---|---|
| NAV & P&L curve | daily, vs SPY and EW-SPX | are we making money? | — (informational; see PSR before believing it) |
| PSR vs 0 and vs benchmark | rolling, daily recompute | is the record distinguishable from luck? | renders next to every return figure |
| MinTRL countdown | "N more trading days before SR≥x claim is testable" | when can we conclude anything? | the expectation-setting widget; never hidden |
| Residual (decision) P&L | post factor/sector/beta attribution (Phase 2+) | are *our decisions* adding value? | pivot checkpoint input (implementation-plan) |
| Drawdown & distance-to-breakers | live; % to pod_halve/pod_halt/fund_derisk/fund_halt | how close are we to automatic de-risking? | <1% distance → standing notice; trip → P8/P12 automatic |
| Gross/net/sector/factor exposures | live vs configuration §6 caps | are we the fund we configured? | gate enforces; dashboard shows headroom |
| Realized vol & rolling beta | 20d/60d | does the book match the regime assumption? | regime_mismatch haircut audit input |
| Hit rate × payoff ratio | per closed trade, monthly roll-up | where does P&L come from (frequency vs magnitude)? | divergence from proposal expectations → PMORT theme |
| Slippage: modeled vs paper-fill vs (P2) measured | per order, monthly report | is our cost model honest? | modeled < realized persistently → recalibrate (backtesting §5) |

## Dashboard 2 — Per-Agent Believability & Calibration (the baseball cards)

Per agent × version tuple, with Wilson/bootstrap intervals always attached:

| Metric | Definition | Action on breach |
|---|---|---|
| Calibration (Brier) | forecast conviction vs realized outcomes | sustained miscalibration → prompt-anchor review (META-01 queue) |
| Stance hit rate @ horizon | per domain bucket | informational until ≥25 obs; then feeds weighting (Phase 3) |
| Memo strip rate | % claims removed by VERIF-01 | > max_stripped_claims_pct trend → agent-quality investigation |
| Role-specific metric | per agent-specifications (BEAR loss-avoidance, MOD premortem recall, PM override record, RISKA heeded-vs-overridden, META proposal hit rate) | each defined with its agent; breaches route to META-01 review |
| Cost per memo/debate/decision | tokens & $ by agent | budget governor enforces; trends inform tiering changes |
| Weight (Phase 3+) | current believability weight w_i with interval | w at clip boundary (w_min/w_max) → review why |

## Dashboard 3 — Protocol & Organization Health (the sycophancy panel)

| Metric | Definition | Question | Alert |
|---|---|---|---|
| Conformity events | post-debate stance flips toward winner without new cited evidence (P5) | is debate persuading or pressuring? | > conformity_flag_threshold per agent → META-01 review |
| Debate-vs-ensemble divergence | live decisions vs shadow ensemble decisions; outcome differential accumulating | does debate earn its cost? | formal readout at G3.3; interim trend monitored |
| Debate rate & skip reasons | % candidates debated; P3 trigger mix | is the debate gate tuned right? | drift from expected ~40% → re-tune thresholds |
| Role violations | capitulations, schema breaches per debate | are adversarial roles holding? | any violation logged; repeat pattern → re-prompt via P11 |
| Ballot margin distribution | histogram of P5 margins | are votes informative or coin flips? | mass near zero → memos may be redundant (diversity problem) |
| Stance correlation matrix | pairwise agent stance correlation, rolling | are "independent" views actually independent? | pair > 0.8 sustained → diversity intervention (model family or prompt separation) |
| PM override ledger | count vs max_overrides_per_month, outcomes | is the PM earning its discretion? | at cap → hard stop until month rolls |
| Verifier disagreement rate | VERIF strip decisions overturned on human spot-check | is the verifier itself reliable? | quarterly audit metric |

## Dashboard 4 — Cost & Budget (the meter)

| Metric | Definition | Alert |
|---|---|---|
| Daily LLM spend vs $50 budget | live accumulation, by tier and agent | 80% → cost_alert; 100% → degrade policy engages (visible event) |
| Cost per decision | full pipeline $ per candidate | > per_decision_budget → degrade engaged; trend → P3 gate re-tune |
| Cache hit rate | memo reuse % | falling → validity windows or content addressing broken |
| Degrade engagements | count + what was degraded | frequent → budget vs ambition mismatch; raise one deliberately |
| Data spend | monthly vs §7 ledger (api-data-sources) | informational; re-verify at vendor renewals |

## Dashboard 5 — Memory & Learning Health

| Metric | Definition | Alert |
|---|---|---|
| Lesson funnel | candidates → probation → active → retired counts, monthly | zero promotions for 2 quarters → PMORT tagging review; cap pressure → ranking working as designed |
| Anchoring audit | corr(memo stance, retrieved-analog outcomes) vs corr(memo stance, evidence strength) | analog corr persistently higher → retrieval format intervention (memory-systems §6) |
| Retrieval relevance | human-sampled: were injected analogs apt? | quarterly spot check, ≥80% apt |
| Believability data growth | scored obs per agent per domain vs the ≥25 threshold | the Phase 3 readiness gauge |
| Rebuild drill result | quarterly rebuild-from-log spot check | any mismatch → P10-style halt of memory writes until resolved |

## Dashboard 6 — Data & Ops Integrity (the boring panel that prevents disasters)

| Metric | Definition | Alert |
|---|---|---|
| Look-ahead audit | nightly query: reads with available_at > decision_ts | **any hit = critical** — halt new cycles, investigate (this is the one metric where the threshold is zero, forever) |
| Ingestion freshness | per-table staleness vs sentinel | stale → P1 gate excludes names automatically; dashboard shows scope |
| Reconciliation status | broker vs ledger, per P10 | mismatch > recon_tolerance → exit-only mode (automatic) |
| Hash-chain verification | event log + memory tables, daily | failure = tampering/corruption → HALT + human |
| Vendor revision events | payload hash changes on re-fetch | logged; spike → vendor quality conversation |
| Loop heartbeats & cycle completion time | deep loop, intraday loop | silent loop = failure (watchdog → P12); completion time trend → capacity planning |
| Node failure & retry rates | per graph node | rising → model/API degradation early warning |

## Alert Routing & Severity

- **SEV-1 (halt-class, automatic action + human page):** look-ahead hit, hash-chain failure, fund breaker trip, reconciliation hard-fail, silent loop. The system acts first (P12/P10 policies), then tells you.
- **SEV-2 (same-day human review):** pod breaker trip, budget 100% degrade, conformity threshold breach, verifier audit failure, escalation timeout fired.
- **SEV-3 (weekly review queue):** calibration drift, strip-rate trends, diversity correlation, cache degradation, cost trends.
- Routing: SEV-1 → push notification + email; SEV-2 → daily digest top section; SEV-3 → weekly review document auto-compiled for the human + META-01.

## Review Cadence Mapping (who looks at what, when)

| Cadence | Panels | Ritual |
|---|---|---|
| Daily (15 min) | D6 status line, D1 breaker distance, yesterday's decision records | skim the cycle log; the system is designed so this is enough |
| Weekly | D3, D4, SEV-3 queue | protocol & cost health; probation queue review |
| Monthly | D1 deep, D2, fill-divergence report | performance-with-honesty-rails read; agent cards |
| Quarterly | D5, Validation Report (backtesting §8), memory review | the two human rituals; META-01 change readouts |

## Implementation Notes
- All metrics derive from the event log (single source); dashboard is a read-only view — consistent with ADR-5, and it means dashboard bugs can never corrupt records.
- Phase 1 ships D1 (minimal), D4, D6, and the conformity counter from D3 — the rest activate with their features. The look-ahead audit and MinTRL countdown are non-negotiable day-one widgets.
- Build: simplest thing that works (e.g., static HTML/Streamlit regenerated nightly from log queries); fancy real-time UIs are Phase 3+ luxuries.

## Open Items
- Exact SEV-2/3 numeric thresholds → tune after 1 month of Phase 1 baselines (pre-committing numbers without baselines invites alert fatigue).
- Decision-quality composite metric for the weighting A/B (G3.1) → pre-register at Phase 3 start, in the Trial Registry.
