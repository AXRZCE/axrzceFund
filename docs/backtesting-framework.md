# backtesting-framework.md — Validation Methodology: How We Decide Whether Anything Here Actually Works

**Status:** v1.0 — Foundation document
**Depends on:** research.md (§IV evidence), architecture.md (PIT store, replay), configuration.md (edge_to_cost_multiple consumer), api-data-sources.md (data PIT grades)
**Feeds into:** validation-criteria.md (phase gates cite these tests), implementation-plan.md (Phase 0 builds this harness first)

**Prime directive:** the most dangerous output this system can produce is not a losing trade — it's a *convincing backtest*. Everything below exists to make self-deception expensive.

---

## 1. The Two Things We Validate (they need different machinery)

**A. Quant signals** (QUANT-01's registry): deterministic, code-computable signals (momentum variants, earnings drift, factor tilts...). These can be backtested classically over decades — full CPCV/DSR machinery applies (§3–5).

**B. The agent pipeline itself** (memos → debate → ballot → PM): LLM-dependent, and therefore **cannot be trusted on any historical period inside the models' training data** (research.md §IV: memorized prices/headlines make in-window "backtests" non-identified). For B, the gold standard is **forward paper trading on post-cutoff data**, with the limited historical techniques of §6 as weak supplements.

Conflating A and B is the field's most common sin (MemGuard-Alpha: <28% of financial-LLM papers control any given bias). Our rule: every reported number is labeled `evidence_class` per §2.

## 2. Evidence Hierarchy (every metric carries its class)

| Class | What it is | Trust level |
|---|---|---|
| E1 | Live forward paper trading, post-model-cutoff, full pipeline | The only class that counts toward phase gates involving agents |
| E2 | Quant-signal backtest under full §3–5 protocol (CPCV + DSR + costs) | Counts for signal-registry admission |
| E3 | Agent-pipeline historical replay with §6 contamination controls | Directional evidence only; never gates anything alone |
| E4 | In-training-window agent backtest, any controls absent | **Banned from reports.** Logged for debugging only, watermarked CONTAMINATED |

## 3. Quant-Signal Backtest Protocol (evidence class E2)

### 3.1 Data discipline (inherited, restated as test conditions)
- Point-in-time everything: queries pass `as_known_at`; the harness runs on the same L1 store as production — **no separate backtest dataset that can drift from live**.
- Universe = point-in-time constituents incl. delisted (Sharadar SP500 history); delisting returns applied (delisted positions exit at last tradable print, not quietly erased).
- Labels: triple-barrier or horizon returns, with label end-times recorded (needed for purging).

### 3.2 Combinatorial Purged Cross-Validation (CPCV) — the default
- N groups (default 10) of contiguous time blocks; all C(N, k) train/test combinations with k=2 test groups → a *distribution* of out-of-sample paths, not one anecdote.
- **Purging:** drop training samples whose label windows overlap any test window. **Embargo:** additionally drop `⟨embargo_pct⟩ = 1%` of samples after each test block (serial-correlation leakage).
- Walk-forward is run *additionally* as a realism check (it respects arrow-of-time deployment), but CPCV is the statistical workhorse — walk-forward alone wastes data and yields one path.

### 3.3 Cost & slippage model (this is what `edge_to_cost_multiple` means)
Per-trade modeled cost, conservative by construction (IEX-grade data ⇒ no microstructure pretensions):
- `cost_bps = spread_term + impact_term + fees`
- `spread_term = ½ × effective_spread_estimate` (per-name, from recent quote data; floor `⟨min_half_spread_bps⟩ = 1bp` for mega-caps).
- `impact_term = ⟨impact_coeff⟩ × σ_daily × √(order_size / ADV)` — square-root impact law, `⟨impact_coeff⟩ = 0.1` initial (industry-standard ballpark; recalibrated quarterly against measured paper-fill divergence once Phase 2 data exists).
- `fees = 0` commissions (Alpaca) + SEC/TAF-style fees on shorts, modeled.
- Sensitivity rule: every E2 result is reported at 1×, 2×, and 3× modeled costs. A signal that dies at 2× costs is not admitted.

### 3.4 Multiple-testing discipline — the Trial Registry
- **Every configuration evaluated is a trial.** The harness auto-logs each (signal, parameterization, universe, period) run to a registry; *you cannot run an unregistered backtest* — the API requires a trial ID.
- **Deflated Sharpe Ratio (DSR):** observed Sharpe is deflated using the registry's trial count N, the variance of trial Sharpes, skewness and kurtosis of returns. Admission requires `DSR p-value < 0.05` *given the true N* — this is the entire point of forcing registration.
- **PBO (Probability of Backtest Overfitting)** via combinatorially symmetric CV on the trial set: report and require `PBO < ⟨max_pbo⟩ = 25%` for registry admission.
- Reference hurdle: Harvey-Liu t ≥ 3.0 for any claimed "new factor" class discovery (we mostly implement known anomalies, where the relevant question is net-of-cost survival, not novelty).

### 3.5 Signal Registry admission checklist (all must pass)
1. E2 protocol complete (CPCV distribution, not cherry-picked path)
2. DSR significant at true trial count; PBO < 25%
3. Survives 2× modeled costs; capacity sanity (signal doesn't require >`⟨max_adv_participation⟩` to express)
4. Economic rationale documented (one paragraph: *why does this edge exist and who is on the other side*) — no rationale, no admission, regardless of stats
5. Regime breakdown reported (bull/bear/high-vol sub-periods) — a signal that only worked 2009–2021 is labeled as such
6. Re-validation schedule assigned (`last_validation_date` drives QUANT-01's memo disclosures; stale validations decay the signal's allowed weight)

---

## 4. Skill-vs-Luck Statistics (applies to E1 and E2 alike)

- **Probabilistic Sharpe Ratio (PSR):** P(true SR > benchmark SR | observed SR, T, skew, kurtosis). Reported on every track record; phase gates specify required PSR levels (validation-criteria.md).
- **Minimum Track Record Length (MinTRL):** the T required for PSR ≥ 95% vs. threshold SR*. Computed live on the paper record and displayed on the dashboard as *"days of track record still needed before this number means anything."* Non-normality matters: negative skew/fat tails inflate MinTRL — the formula uses observed moments, not Gaussian fantasy. Expectation-setting: a true-SR≈1 strategy with ugly moments can need *years*; the dashboard saying "insufficient evidence" for months is correct behavior, not a bug.
- **Benchmark-relative inference:** alpha t-stats vs. SPY and equal-weight SPX (both, per configuration §1), with HAC (Newey-West) standard errors; plus bootstrap confidence intervals on Sharpe and max drawdown (block bootstrap, preserving autocorrelation).
- **Attribution split:** P&L decomposed into market beta, sector, factor tilts (Phase 2+ factor model), and residual ("our decisions"). Only residual P&L counts as evidence of skill.

## 5. Paper-Trading Realism Audit (making E1 actually gold-standard)

Forward paper results are only as good as their realism. Standing audits:
- **Fill divergence:** broker paper fill vs. our modeled fill logged on every order (api-data-sources §2.1); monthly report; if modeled costs are systematically *lower* than even optimistic paper fills, the cost model is recalibrated upward immediately.
- **Latency honesty:** decisions stamped at deep-loop completion; orders executed next session per P7 — the harness verifies no order ever references information stamped after its decision_ts (an automated audit query over the event log, run nightly).
- **No quiet restarts:** every halted/erroneous cycle stays in the record. The track record includes operational failures, because live trading would too.
- **Dividend/borrow accounting:** dividends credited, short borrow costs debited at modeled rates — paper brokers often ignore these; we don't.

## 6. LLM Contamination Controls (evidence class E3 — and why it's capped)

For any agent-pipeline evaluation on historical data:
- **C1 — Post-cutoff only (preferred):** evaluate only on dates after the *latest* training cutoff among all models in the pipeline. This converts E3 → E1-like validity but shortens usable history; with heterogeneous models, the binding cutoff is the max — recorded per run.
- **C2 — Entity neutering (supplement):** strip tickers, company names, person names, and absolute dates from all documents fed to agents; replace with stable pseudonyms. Reduces—does not eliminate—recognition (models can identify famous episodes from context). Any C2 run is labeled `neutered` and treated as directional.
- **C3 — Memorization probes (tripwire):** before an E3 run on period P, probe each model: elicit closing prices / headline recall for P. Probe hit-rate above `⟨memorization_threshold⟩ = chance + margin` disqualifies that model for that period.
- **C4 — Cross-model disagreement screen:** signals/claims that only "work" for models whose training window covers P (and fail for post-cutoff models) are flagged as memorization artifacts.
- Hard rule: **E3 never gates a phase, never admits a signal, never increases an agent's believability.** Its only legitimate uses: debugging prompts, comparing protocol variants (debate vs. no-debate) where contamination plausibly affects both arms equally — and even then, conclusions are provisional until E1 confirms.

## 7. Protocol-Level Experiments (evaluating the *organization*, not the stocks)

The same rigor applies to our own design choices. Standing A/B harness (run within live paper flow, randomized at candidate level where safe):
- Debate vs. independent-ensemble-only (the central question from research.md §II — does P4 earn its cost?)
- Equal weights vs. believability weights (the Phase 3 gate experiment)
- Memo-with-memory vs. memo-without (does episodic retrieval help or anchor?)
Each experiment pre-registers its metric, sample size target, and stopping rule in the Trial Registry — agent-organization choices get the same anti-p-hacking discipline as signals.

## 8. Reporting Standards (what a "result" must look like)

Every reported performance number carries: `evidence_class`, period, N trials (registry), DSR/PSR, costs assumption (1×/2×/3×), regime breakdown, MinTRL status, and the replay tuple (config/prompt/model/code versions). A number missing any field is not a result; dashboards render it greyed-out with the missing fields named. Quarterly, a **Validation Report** consolidates: registry statistics (how many trials died, and where), cost-model recalibration, contamination-probe results, and protocol-experiment readouts — this is the document a skeptical outside reviewer would ask for, so we write it as if they will.

## 9. Open Items
- `⟨impact_coeff⟩` recalibration procedure once Phase 2 fill data accumulates (owner: Phase 2)
- Factor model selection for §4 attribution (Phase 2; candidates: open-source Barra-style vs. Fama-French 5+Mom from Ken French library — PIT caveats documented at selection)
- Conformal-prediction wrapper for signal uncertainty (Phase 3 candidate, research.md Tier 1)
- Exact `⟨memorization_threshold⟩` calibration per model family (Phase 1, cheap to measure)
