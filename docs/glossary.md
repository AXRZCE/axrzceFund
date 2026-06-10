# glossary.md — Shared Vocabulary for the Multi-Agent Fund

**Status:** v1.0 — Tier 3 document
**Purpose:** one definition per term, as *used in this project* (where our usage is narrower than the textbook's, ours wins here). Each entry names its home document for depth. Organized by category; alphabetical within.

---

## 1. Statistics & Validation

- **Bootstrap (block):** resampling contiguous blocks of returns to build confidence intervals while preserving autocorrelation. Used for Sharpe/drawdown CIs. → backtesting §4
- **Brier score:** mean squared error of probabilistic forecasts; our core calibration metric — lower is better, and it punishes confident wrongness. → memory §5.1
- **CPCV (Combinatorial Purged Cross-Validation):** cross-validation over all train/test combinations of time-blocks, with purging and embargo, yielding a *distribution* of out-of-sample paths instead of one. The default E2 test. → backtesting §3.2
- **DSR (Deflated Sharpe Ratio):** Sharpe ratio statistically discounted for the number of trials run, trial-Sharpe variance, skewness, kurtosis, and sample length. Admission requires DSR significance *at the true trial count* — hence the Trial Registry. → backtesting §3.4
- **Embargo:** a buffer of samples dropped *after* each test window so serial correlation can't leak test information into training. Companion of purging. → backtesting §3.2
- **Evidence classes (E1–E4):** our trust taxonomy. E1 = post-cutoff forward paper (gold). E2 = full-protocol quant backtest. E3 = contamination-controlled agent replay (directional only). E4 = uncontrolled in-window agent backtest (banned from reports, watermarked CONTAMINATED). → backtesting §2
- **HAC / Newey-West:** standard-error correction for autocorrelated, heteroskedastic returns; applied to alpha t-stats. → backtesting §4
- **KS test (Kolmogorov–Smirnov):** distribution-comparison test; used to check a live signal's behavior against its CPCV path distribution (G2.2b fidelity bands). → validation G2
- **MinTRL (Minimum Track Record Length):** how long a track record must be before its Sharpe claim is statistically testable at a confidence level, given observed skew/kurtosis. Rendered as a dashboard countdown; the anti-impatience widget. → backtesting §4
- **PBO (Probability of Backtest Overfitting):** probability that the in-sample-best configuration underperforms out-of-sample; admission requires < 25%. → backtesting §3.4
- **PSR (Probabilistic Sharpe Ratio):** P(true Sharpe > threshold | observed record and its moments). Reported beside every return figure. → backtesting §4
- **Purging:** removing training samples whose label windows overlap a test window — kills label leakage in path-dependent data. → backtesting §3.2
- **Trial Registry:** append-only ledger of every backtest configuration ever evaluated; the harness API refuses unregistered runs. Exists so DSR's N is true. Also pre-registers protocol experiments. → backtesting §3.4, §7
- **Triple-barrier labeling:** labeling returns by which of profit-take / stop / time-horizon barriers is hit first; produces the label end-times purging needs. → backtesting §3.1
- **Wilson interval:** confidence interval for proportions (hit rates); the reason no naked hit rate ever appears on a dashboard. → memory §5.2

## 2. Finance & Portfolio

- **ADV / ADV participation:** average daily volume; our orders are capped at 2% of 20-day ADV — beyond that, our cost model loses authority. → configuration §6
- **Alpha / residual P&L:** P&L unexplained by market beta, sector, and factor exposures. The only P&L that counts as evidence of skill, and the quantity pivot reviews interrogate. → backtesting §4
- **Believability (weight):** an agent's vote weight, computed solely from its logged forecast outcomes (calibration × hit rate × contribution), clipped to [0.5, 2.0]. Bridgewater's concept, made incorruptible. OFF until Phase 3's experiment justifies it. → configuration §4, memory §5
- **Breaker (drawdown circuit-breaker):** code-enforced automatic de-risking at fixed drawdown levels (pod −5% halve, −7.5% flatten; fund −6% de-risk, −10% halt). Cannot be argued with; loosening is human-only. → configuration §7
- **Factor model:** decomposition of returns into systematic exposures (market, size, value, momentum...); powers attribution and exposure caps from Phase 2. → backtesting open items
- **Gross / net exposure:** sum of |long| + |short| vs. long − short, as % NAV. Caps: 150% gross, ±30% net. → configuration §6
- **HWM (high-water mark):** peak NAV (or pod equity) from which drawdowns are measured. → configuration §7
- **Market impact (square-root law):** modeled price impact ∝ σ·√(size/ADV); our impact_coeff starts at 0.1 and is recalibrated against measured fills. → backtesting §3.3
- **NAV:** net asset value; paper fund starts at $1M. → configuration §1
- **Pod:** a semi-autonomous strategy/sector bucket with its own P&L, capital, and breakers — Millennium's unit of accountability, ours from Phase 2. We halt pods rather than terminate them (learning data is kept). → architecture, implementation-plan
- **Slippage:** realized fill price vs. decision-time reference price; tracked three ways (modeled / broker-paper / measured). → backtesting §5
- **Survivorship bias:** evaluating on today's surviving companies only, silently deleting the dead — why delisted coverage (Sharadar) is a hard requirement. → api-data §1

## 3. LLM & Agent Concepts

- **Conformity event:** a voter's post-debate stance flip toward the debate's apparent winner without newly cited evidence — our unit of measured sycophancy. → P5, monitoring D3
- **Contamination (training-data):** an LLM "predicting" a historical period it memorized in training; the reason agent backtests are class-E3 at best. → backtesting §6
- **Entity neutering:** stripping names/tickers/dates from documents so a model can't recognize the historical episode; a weak supplement (C2), never a substitute for post-cutoff testing. → backtesting §6
- **Hallucination:** fluent fabrication of facts; structurally countered by citation-or-it-didn't-happen plus the Verifier. → architecture §8.4
- **Heterogeneity invariant:** Bull and Bear on different model families, PM on a third, judge ≠ judged. Frozen Set item. → configuration §3, §9
- **LLM-as-judge:** using a model to score outputs (debates, claims); known biases (verbosity, position) mitigated by rubrics, masking, randomized order. → agent-spec §6.5
- **Memorization probe (C3):** directly asking a model to recall prices/headlines from a period before trusting any evaluation on that period. → backtesting §6
- **RAG (retrieval-augmented generation):** agents cite retrieved documents (filings, news) rather than internal memory; our anti-hallucination substrate. → architecture L1
- **Sycophancy:** an LLM's tendency to agree with perceived consensus or authority over its own assessment; our #1 ranked agent risk. → research §II, failure-modes 1.1
- **Version tuple:** (agent_id, prompt_version, model_version) — the identity unit for track records; change the model, start a new (linked, discounted) record. → memory §5.2

## 4. System & Data Terms

- **as_of / available_at:** event time vs. knowledge time — the two timestamps on every L1 row. The entire look-ahead defense reduces to "never read available_at > decision_ts." → architecture Principle 5
- **as_known_at:** the mandatory parameter on data queries that makes look-ahead impossible to express in code. → api-data §4
- **decision_ts:** the cycle's fixed information boundary; all reads and stamps reference it. → architecture §7.1
- **Deep loop / light loop:** the daily full-debate cycle (the brain) vs. the continuous intraday monitor/executor (the reflexes — no new entries, ever, in Phases 1–2). → architecture §6
- **Degrade (policy):** the budget governor's graceful response to hitting cost ceilings — fewer debate rounds, deferred candidates — never silent overspend. → architecture §5
- **Event log:** the append-only, hash-chained record of every system event; the source of truth from which all stores and dashboards are derived views. → architecture L2, ADR-5
- **Fail closed:** on any failure, the affected pipeline stops in a no-new-risk state (NO-TRADE / exit-only / HALT); the system never guesses its way to an order. → architecture §11
- **Frozen Set:** the constitutional layer of configuration — seven items only the human may amend, and META-01 may never propose against. → configuration §9
- **PIT (point-in-time):** data as it was knowable on a date, including later-restated values in their original form. PIT grades: native (Sharadar, EDGAR) > ingestion-stamped (news). → api-data §1
- **Replay tuple:** (config_version, prompt_version, model_version, code_version) + logged memory retrievals — everything needed to reconstruct any past decision exactly. → architecture §7.3
- **SEV-1/2/3:** alert severities — halt-class with automatic action / same-day review / weekly queue. → monitoring
- **Staleness sentinel:** per-table freshness check gating each cycle; stale names are auto-excluded. → api-data §6
- **Trial ID:** the registry handle without which the harness will not run a backtest. → backtesting §3.4

## 5. Protocol & Workflow Terms

- **P1–P12 (one-liners):** P1 cycle open & screening · P2 independent memos · P3 debate-eligibility gate · P4 adversarial debate · P5 sealed weighted ballot · P6 PM synthesis & sizing · P7 risk opinion → compliance → code gate · P8 intraday monitoring & escalation · P9 post-mortem & learning · P10 cycle close & reconciliation · P11 change management · P12 halt & recovery. → decision-protocols
- **CONTESTED:** ballot outcome when the weighted margin < 20%; caps the trade at pilot size (0.5% NAV). → P5/P6
- **DEBATE_FAILED:** a candidate whose debate could not complete after retry; tradable only at the undebated cap (0.75% NAV). → P4
- **Escalation (mini-graph):** the only intraday LLM decision — event memo + risk opinion + gate, outputs limited to hold/reduce/hedge/exit, 10-minute timeout defaulting to reduce-by-half. → P8
- **Gate (the code gate):** the deterministic L5 pre-trade check (limits, exposures, liquidity, breaker state) that is the only path to the broker and accepts no appeals. → architecture L5, P7
- **Independence baseline:** each agent's pre-debate stance snapshot from P2 — the benchmark that makes conformity measurable and the shadow ensemble computable. → P2
- **NO-TRADE:** an explicit PM pass with reasons and reopening conditions — a logged decision, not an absence of one; scored for opportunity cost. → P6
- **Pre-mortem:** the Moderator-extracted "this trade fails if..." scenarios with observable early-warning indicators; its hit rate is MOD-01's core metric. → P4
- **Sealed ballot:** votes cast without sight of any other ballot, unsealed simultaneously — structural anti-conformity. → P5
- **Shadow ensemble:** the parallel decision computed from independent memos alone (no debate), logged-not-traded since day one; the control arm of the debate-value experiment. → implementation-plan Phase 1, G3.3

## 6. Memory & Learning Terms

- **Anchoring audit:** the standing test of whether memo stances track retrieved-analog outcomes more than current evidence — memory acting as a bias instead of a resource. → memory §3.2
- **Episode:** the immutable per-trade record (thesis, debate, ballot, outcome, post-mortem); the unit of episodic memory. → memory §3.1
- **Lesson (probation → active → retired):** a generalizable post-mortem finding: 3 independent confirmations to activate, contradiction-tracked, demotable, capped at 40 active. Lessons are hypotheses with provenance, never facts. → memory §4
- **Setup fingerprint:** the embedding + tags over which episodic similarity retrieval runs. → memory §3.1
- **Luck/skill assessment:** PMORT-01's separation of process quality from outcome; luck-flagged wins cannot confirm lessons ("a profitable trade with a refuted thesis is a loss that paid"). → agent-spec §6.3

## 7. Organizational Concepts (inherited from research.md)

- **Idea meritocracy / believability-weighted decision-making:** Bridgewater's principle that votes should be weighted by demonstrated, domain-specific track record — our P5, with politics replaced by computation.
- **Issue Log / Pain Button (Bridgewater):** systematic error-recording and post-loss reflection — our event log + P9 ancestry.
- **Pod model (Millennium/Citadel):** independent teams, centralized un-appealable risk — our pods + L5 gate ancestry.
- **Single-model collaboration (Renaissance):** every validated insight benefits the whole fund — our shared semantic memory and signal registry ancestry.
