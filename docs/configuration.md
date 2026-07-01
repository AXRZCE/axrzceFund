# configuration.md — Fund Bylaws: Every Tunable Parameter, Its Value, and Its Rationale

**Status:** v1.0 — Foundation document (values = Phase 1–2 defaults)
**Depends on:** decision-protocols.md (every `⟨parameter⟩` named there is valued here), architecture.md (ADR-2 tiers, ADR-8 brokers)
**Change control:** this file is versioned (`config_version`). Changes deploy only at cycle boundaries via protocol P11. The **Frozen Set** (§9) can be amended by the human owner only — never by META-01 proposals.

Format per parameter: `name = value` — *rationale* — (protocol where used).

---

## 1. Mandate & Universe

- `universe = S&P 500 constituents, point-in-time` — large-cap only at first: best data quality, deepest liquidity, least slippage-model uncertainty; expansion to Russell 1000 is a Phase 3 decision. (P1)
- `min_adv_usd = $20M` — at our sizes, anything below this makes the slippage model the dominant error term. (P1)
- `min_price = $5.00` — avoids microstructure weirdness and borrow problems in low-priced names. (P1)
- `shorts_enabled = true, easy-to-borrow only` — short theses keep the Bear honest, but hard-to-borrow names add a cost model we haven't validated. (P1)
- `instruments = common stock + sector ETFs (hedging only)` — no options in Phases 1–2; a deep-hedging overlay is a Phase 4 candidate (research.md Tier 1). (P6/P8)
- `starting_paper_nav = $1,000,000` — large enough for realistic position granularity, small enough that ADV-participation constraints rarely bind, keeping early data clean. 
- `benchmarks = SPY (primary), equal-weight SPX (secondary)` — both, because cap-weight alone flatters/punishes unfairly depending on breadth regime. (validation-criteria.md)

## 2. Cycle & Candidates

- `max_candidates_per_cycle = 10 new + all held positions` — attention and cost quality beat coverage; 10 debated names/day is already ~30 T2 debates' worth of tokens at full debate rate. (P1)
- `min_memos_required = 3` — below three independent views, "ensemble" is a euphemism. (P2)
- `max_stripped_claims_pct = 30%` — a memo losing a third of its factual claims to verification is not evidence, it's noise with citations. (P2)
- `monitor_interval = 60s` — paper-trading reflex speed; tighten only if stop-slippage measurement says it matters. (P8)
- `aging_review_days = 30` — any position older than a month without a closed outcome gets a forced review; thesis drift is real. (P9)

## 3. Model Assignment & Cost Budgets (ADR-2)

Tier assignments by **family role**, not pinned versions (versions pinned in a deployment manifest, stamped as `model_version`):

- `T1_fast = small-model class of any major family` (e.g., Gemini Flash-Lite / GPT-5-mini / DeepSeek-Flash class) — triage, extraction, screening, intraday classification.
- `T2_reasoning_A = Chinese open-weight frontier class` (DeepSeek / GLM) → **BULL-01**, plus half the research pool. Open-weight is a deliberate replay + decorrelation choice (pinnable/self-hostable frozen artifact); **gated on golden-day FINANCIAL-task validation and a Western inference host before any high-stakes role** (backtesting §6; benchmarks are coding/math, do not transfer).
- `T2_reasoning_B = OpenAI frontier class` → **BEAR-01**, plus the other half of the research pool.
- `T2_reasoning_C = Google frontier class` → **PM-01** and MOD-01 — the synthesizer/referee sits outside both debating families. (agent-specifications §4–5)
- `T3_judge = strongest available family ≠ judged agents per call` → VERIF-01, PMORT-01, META-01; the orchestrator resolves the family at call time to maintain judge ≠ judged.
- Heterogeneity invariant (restated as config): `family(BULL) ≠ family(BEAR)`, `family(PM) ∉ {family(BULL), family(BEAR)}` where the provider set allows.

> **ADR-2 amendment (2026-06-25): Anthropic dropped from the agent roster; the three families are now Google / OpenAI / Chinese-open-weight.** *Rationale:* on Jun-2026 price-performance, Anthropic wins no value tier (Gemini 3.x and DeepSeek/GLM dominate $/quality), so it is not in the fund's agent roster (it may return later as an optional 4th decorrelation family). The decorrelation **principle is unchanged** — three distinct families so BULL≠BEAR and the referee sits outside both. **WP2 (research only, no debate) runs Western-only** (Google + OpenAI); the Chinese open-weight family (T2_A) is piloted + fixture-validated at WP3 — that financial-fixture validation is WP3's **gating first task** — where the debate makes family choice load-bearing. Exact per-role version pins live in `deploy/model_manifest.yaml`. (The Claude Code orchestration/dev layer is a separate tool, **not** part of this roster.)

Budgets (budget governor, architecture §5):
- `daily_llm_budget_usd = $50` — Phase 1 ceiling; forces the P3 debate-gate discipline to actually matter. Expect ~$25/day typical at 10 candidates with ~40% debate rate.
- `per_decision_budget_usd = $8` — one candidate's full pipeline (memos → debate → ballot → PM) should not exceed this; breach degrades gracefully: fewer debate rounds first, then candidate deferred to tomorrow.
- `budget_breach_policy = degrade, never silently exceed` — (architecture §5)
- `cost_alert_pct = 80%` of daily budget → dashboard alert. (monitoring-metrics.md)

## 4. Debate & Ballot Parameters

- `debate_dispersion_threshold = 0.30` — conviction-weighted stance dispersion above this means genuine disagreement worth paying for. Start moderately permissive; META-01 will have data to tune it. (P3)
- `debate_size_threshold_pct_nav = 1.5%` — anything bigger than a starter position gets debated regardless of agreement. (P3)
- `max_debate_rounds = 3` — opening/rebuttal/closing; research.md shows diminishing returns beyond ~3 rounds and rising conformity risk. (P4)
- `undebated_size_cap_pct_nav = 0.75%` — DEBATE_FAILED names trade at half a starter position at most. (P4/P6)
- `ballot_margin_threshold = 0.20` — weighted-score margin below 20% of total cast weight = CONTESTED. (P5)
- Believability weighting: `weighting_enabled = false` (Phase 1–2) — equal weights until track records exist; flipping this to true is *the* Phase 3 gate decision. `min_observations_for_weighting = 25` scored calls per agent per domain — below that, weight differences are sampling noise (research.md MinTRL logic applied to agents). `α = 1.0, β = 1.0, γ = 0.5` — calibration and hit rate matter equally; contribution gets a half-exponent because it's noisiest. `w_min = 0.5, w_max = 2.0` — a 4:1 max influence spread; no dictators, no mutes. (P5)
- `conformity_flag_threshold = 3 unexplained flips / 20 ballots` — persistent post-debate flipping toward winners without new evidence triggers META-01 review. (P5)

## 5. Sizing & Proposal Discipline

- `base_size_pct_nav = 1.0%` — starter position; fractional-Kelly spirit: assume edge estimates are overstated. (P6)
- `conviction_factor range = 0.5×–1.5×` base — conviction modulates, it doesn't multiply unboundedly. (P6)
- Haircuts (multiplicative, downward only): `contested = ×0.5` (also hard cap below), `regime_mismatch = ×0.7`, `unresolved_bear_crux = ×0.7`, `liquidity_thin = ×0.8`. (P6)
- `contested_size_cap_pct_nav = 0.5%` — CONTESTED names are pilots, not positions. (P6)
- `edge_to_cost_multiple = 3×` — expected edge must be ≥3× estimated round-trip cost; below that you're trading for the broker's benefit (even on paper, we simulate the costs). (P6)
- `max_overrides_per_month = 2` — PM defiance of the ballot is a scarce resource by construction. (P6)
- `max_position_pct_nav = 5%` (hard gate) — single-name blowup containment. (P7)
- `max_new_position_pct_nav = 2.5%` — full 5% must be earned through adds on a working thesis, never bought day one. (P6/P7)

## 6. Portfolio & Risk Limits (the code gate's table — P7)

- `max_sector_pct_nav = 20%` gross per GICS sector — sector bets are allowed, sector funds are not (we're not running a thematic book).
- `max_gross = 150%` NAV — modest leverage room for hedged pairs; far below pod-shop 4–8× because our cost/borrow models are unproven.
- `net_band = ±30%` NAV — directional tilt allowed, beta fund not. Tighter (±20%) is the Phase 3 target once hedging via sector ETFs is routine.
- `max_adv_participation_pct = 2%` of 20-day ADV per day per name — keeps the slippage model honest; with $1M NAV and $20M+ ADV names this should never bind, which is intentional (binding liquidity constraints would mean our paper fund is simulating a fund we aren't).
- `factor_exposure_caps = |beta-adjusted net| ≤ 0.4, |size/value/momentum z| ≤ 1.0 each` — Phase 2+ when the factor model lands; Phase 1 proxies with the net band.
- `min_clamp_ratio = 0.8` — the gate may trim a proposal by up to 20%; needing more means the proposal was wrong → reject with reason. (P7)
- `recon_tolerance = $0.01 per position, 1 share quantity` — paper brokers should reconcile exactly; any persistent mismatch is a bug, and bugs get exit-only mode. (P10)

## 7. Drawdown Breakers (P8) — the Millennium discipline, scaled to us

Pod = a sector/strategy bucket once Phase 2 pods exist; Phase 1 treats the whole book as one pod.

- `pod_halve_dd = −5%` from pod high-water mark → pod gross halved automatically.
- `pod_halt_dd = −7.5%` → pod flattened, no new entries until human review.
- `fund_derisk_dd = −6%` from fund HWM → `derisk_gross = 75%` of normal gross cap; new-entry sizes ×0.5.
- `fund_halt_dd = −10%` → HALT (P12).
- `cooldown_cycles = 3` — after any HALT recovery, three exit-only cycles before new entries; re-entry into risk is the moment humans historically blow up, so the system is forbidden from hurrying it. (P12)
- Rationale for levels: tighter than most human funds (the research point — we *can* be stricter because no one's ego is invested in "riding it out"), looser than Millennium's pod terms because our pods are sectors of one strategy, not independent businesses; termination is replaced by halt+review since deleting a pod deletes its learning data.

## 8. Escalation, Change Management, Memory

- `escalation_timeout = 10 min` → on timeout `default_derisk_pct = 50%` reduction of the affected position — when in doubt and out of time, be smaller. (P8)
- `change_review_horizon = 4 weeks` — META-01 proposals are judged against their own `expected_effect` after a month. (P11)
- `lesson_min_occurrences = 3` — a "lesson" seen once is an anecdote; three independent confirmations before semantic-memory promotion. (P9)
- `episodic_retrieval_k = 5, recency_half_life = 180d` — how many analog trades agents see and how fast old ones fade; memory-systems.md owns the mechanics. (P2/P6)

## 9. The Frozen Set (human-only amendments; META-01 may never propose against these)

1. The enforcement boundary itself (architecture ADR-4/5/6: code-only gate, append-only log, point-in-time discipline).
2. Believability formula structure and its computation from outcomes (parameters §4 are tunable by P11; the *principle* that weights come only from logged outcomes is not).
3. All breaker levels in §7 may only be made **tighter** by P11; loosening is human-only with written rationale.
4. Heterogeneity invariant (§3).
5. `intraday_new_entries = forbidden` (Phases 1–2; lifting it is a Phase 3+ human decision against validated evidence).
6. META-01's own constraints (agent-specifications §6.4).
7. Kill-switch authority and P12 human-recovery requirement.

## 10. Data, Broker, and Infrastructure Settings

- `broker_primary = Alpaca paper`, `broker_secondary = IBKR paper` — both behind `BrokerInterface` from day one (ADR-8); secondary validated weekly by mirroring a sample of orders.
- `market_data = Alpaca (IEX feed) Phase 1 → Polygon Phase 2` — IEX-only is fine for daily-cadence decisions; consolidated-tape accuracy starts mattering when slippage measurement does. Live feed only — backtest/historical prices come from Sharadar SEP. (api-data-sources.md owns details)
- `fundamentals = Sharadar SFA bundle via Nasdaq Data Link (purchased June 2026, $79/mo)` — SF1 fundamentals with native `available_at` (filing-date) semantics, plus SEP/ACTIONS/TICKERS/SP500-history; key in `NASDAQ_DATA_LINK_API_KEY` env var only. The former #1 open procurement item is resolved.
- `filings/news = EDGAR direct + news API (TBD)` with ingestion-time stamping.
- `storage = DuckDB/Parquet + SQLite event log (Phase 1) → Postgres (Phase 2)` (ADR-7).
- `event_log_integrity = daily hash chain check` (P10).
- `timezone = America/New_York for all market logic; UTC in the event log` — one explicit rule now prevents a hundred subtle bugs later.
- `secrets = environment/secret-manager only; never in config files or prompts` — and never in the event log. The vendor-data commit policy (fixtures gitignored + hash-locked, the commit-guard, the public-repo scrub) is in [data-governance.md](data-governance.md).

## 11. Versioning & Deployment Rules

- Every run stamps `config_version` (this file's hash), `prompt_version` per agent, `model_version` per call, `code_version` (git SHA) — the replay tuple (architecture §7.3).
- Config changes: PR-style diff + rationale → human approval → activates at next cycle open (P11). Emergency path per P11.4.
- A config value used in code but absent from this file is a build error by policy — this document is exhaustive by definition, and the test suite should enforce that.

## 12. Parameter Cross-Reference (audit aid)

| Protocol | Parameters valued here |
|---|---|
| P1 | universe, min_adv_usd, min_price, max_candidates_per_cycle |
| P2 | min_memos_required, max_stripped_claims_pct |
| P3 | debate_dispersion_threshold, debate_size_threshold_pct_nav |
| P4 | max_debate_rounds, undebated_size_cap_pct_nav |
| P5 | weighting_enabled, min_observations_for_weighting, α/β/γ, w_min/w_max, ballot_margin_threshold, conformity_flag_threshold |
| P6 | base_size, conviction_factor, haircuts, contested cap, edge_to_cost_multiple, max_overrides_per_month, max_new_position |
| P7 | position/sector/gross/net/ADV/factor caps, min_clamp_ratio |
| P8 | monitor_interval, breakers (§7), escalation_timeout, default_derisk_pct |
| P9 | aging_review_days, lesson_min_occurrences |
| P10 | recon_tolerance |
| P11 | change_review_horizon |
| P12 | cooldown_cycles |

## Open Items
- ~~Point-in-time fundamentals vendor decision~~ — resolved June 2026: Sharadar SFA purchased (api-data-sources.md §4).
- Slippage/cost model parameters → backtesting-framework.md (the `edge_to_cost_multiple` check needs the cost model to mean anything).
- Factor model choice for §6 caps → backtesting-framework.md / Phase 2.
- Dashboard thresholds referencing these values → monitoring-metrics.md.
