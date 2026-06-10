# agent-specifications.md — Agent Roster, Contracts, and Prompt Anchors

**Status:** v1.0 — Foundation document
**Depends on:** research.md (evidence), architecture.md (pools, permissions, tiers, state model)
**Feeds into:** decision-protocols.md (how these agents interact), configuration.md (parameter values), memory-systems.md (what they store/retrieve)

---

## 1. How to Read This Document

Each agent is specified with the same eight fields, so building an agent is a fill-in-the-blanks exercise:

- **ID / Pool / Tier** — stable identifier, pool from architecture.md §3, model tier from §5 (T1 fast / T2 reasoning / T3 judge).
- **Mission** — the one-sentence job. If an output doesn't serve the mission, the agent shouldn't produce it.
- **Reads** — exactly what context it receives. Anything not listed is deliberately withheld (isolation is a feature).
- **Writes** — its output contract (schema). Unparseable output = node failure = fail closed (architecture.md §11).
- **Believability metrics** — what the believability store scores this agent on (architecture.md L2). These define what "good" means for the agent.
- **Failure modes & guards** — the known ways this agent goes wrong (research.md §II) and the structural countermeasure.
- **Prompt anchors** — the personality, constraints, and standing orders that go into its system prompt. Anchors here are design-level; full prompt text is an implementation artifact, versioned as `prompt_version`.
- **Cannot** — explicit non-permissions, because what an agent *can't* do is as load-bearing as what it can.

**Universal rules (inherited by every agent):**
1. Every factual claim must cite an L1 document ID (`evidence: [doc_id, ...]`). Uncited claims are stripped by the Verifier before anyone downstream sees them.
2. Every output includes `confidence` ∈ [0,1] and is scored later for calibration — agents are told their confidence is graded, which is itself a calibration-forcing device.
3. Every output carries `agent_id`, `model_version`, `prompt_version`, `cycle_id`, `decision_ts`.
4. No agent may reference data with `available_at > decision_ts` (enforced by L1, restated in every prompt).
5. No agent communicates with another agent directly; all communication flows through typed state (architecture.md §8).

---

## 2. Shared Output Schemas

### 2.1 ResearchMemo (all Research-pool agents)
```yaml
memo:
  ticker: str | "MARKET"          # MARKET for macro
  stance: long | short | neutral | avoid
  conviction: 0.0-1.0
  horizon_days: int
  thesis: str                      # <= 150 words, falsifiable
  key_claims:                      # 3-7 claims max
    - claim: str
      evidence: [doc_id]
      claim_type: fact | inference | estimate
  catalysts: [{event: str, expected_window: date-range}]
  invalidation_conditions: [str]   # observable, checkable by code where possible
  risks: [str]
  what_would_change_my_mind: str   # mandatory; epistemic forcing function
```

### 2.2 DebateTurn (Bull/Bear)
```yaml
turn:
  round: int
  position: bull | bear
  arguments: [{point: str, evidence: [doc_id], attacks: memo_claim_ref | null}]
  concessions: [str]               # what the opponent got right (Moderator enforces non-empty by round 2)
  steelman_of_opponent: str        # mandatory each round
```

### 2.3 TradeProposal (Portfolio Manager)
```yaml
proposal:
  ticker: str
  direction: long | short
  size_pct_nav: float              # proposed; gate may clamp
  entry_plan: {type: market_open | limit | vwap_window, params: {}}
  stop_loss: price | pct
  invalidation_conditions: [str]   # union of surviving conditions from memos/debate
  horizon_days: int
  thesis: str
  premortem_top_risks: [str]       # from Moderator's pre-mortem
  expected_edge_bps: int           # forces explicit edge claim vs costs
  ballot_summary: {weighted_score: float, dissent: str}
```

### 2.4 RiskOpinion / PostMortem / Attribution — defined inline with their agents (§5–6).

---

## 3. Research Pool (independent, parallel, isolated)

### 3.1 MACRO-01 — Macro Analyst
- **Pool/Tier:** Research / T2
- **Mission:** Characterize the current market regime and its implications for equity factor and sector positioning.
- **Reads:** L1 macro series (rates, curves, inflation prints, ISM, claims), index/sector price history, VIX/term structure, L2 semantic memory (regime playbooks). Does **not** read other agents' memos.
- **Writes:** One `ResearchMemo` with `ticker: MARKET` + a `regime_label` extension: `{regime: risk_on|risk_off|transition|stress, vol_regime: low|elevated|crisis, favored_factors: [...], disfavored_sectors: [...]}`.
- **Believability metrics:** regime-call hit rate vs. realized 20-day outcomes; calibration of `conviction`; usefulness score (how often PM cites it in winning vs. losing trades).
- **Failure modes & guards:** narrative addiction (compelling macro stories with no testable content) → guard: `invalidation_conditions` must be observable data, not vibes; recency bias → guard: episodic retrieval of similar past regimes is injected into its context.
- **Prompt anchors:** "You are paid for *falsifiable* regime claims, not commentary. Every regime call must specify what data would prove it wrong and by when."
- **Cannot:** recommend individual tickers; see candidate list (prevents anchoring the whole cycle).

### 3.2 FUND-{SECTOR} — Sector Fundamental Analysts (one per sector, e.g., FUND-TECH, FUND-FIN, FUND-HLTH, FUND-ENE, FUND-CON, FUND-IND)
- **Pool/Tier:** Research / T2
- **Mission:** Produce a point-in-time fundamental view of assigned candidates: valuation, earnings quality, balance-sheet risk, filing red flags.
- **Reads:** Candidate tickers in its sector; L1 point-in-time fundamentals, filings/transcripts via time-bounded RAG; episodic memory of past trades in those names. Not other memos.
- **Writes:** One `ResearchMemo` per assigned candidate, plus `valuation_block: {method: dcf|multiples|sotp, fair_value_range: [low, high], key_assumptions: [...]}`.
- **Believability metrics:** direction hit rate at memo horizon; fair-value-range coverage (did price enter range?); calibration; red-flag precision (flags that later mattered).
- **Failure modes & guards:** stale-knowledge hallucination (citing remembered, not retrieved, fundamentals) → guard: Verifier rejects numbers without document IDs; story-stock seduction → guard: `valuation_block` is mandatory, an explicit number with assumptions.
- **Prompt anchors:** "Numbers you cannot cite do not exist. Your fair-value range will be graded against reality. State the assumption that, if wrong, breaks your thesis."
- **Cannot:** opine outside its sector; adjust for what 'the market thinks' (that's Sentiment's job — separation keeps signals decorrelated).

### 3.3 QUANT-01 — Quant Researcher
- **Pool/Tier:** Research / T2 (its *signals* are precomputed code; the agent interprets)
- **Mission:** Report what the validated signal library says about each candidate, with exposures and historical analog context — interpretation, never improvisation.
- **Reads:** Outputs of the validated signal pipeline (factor scores, momentum/reversal states, earnings-drift flags), factor-exposure decomposition, backtest stats of each signal (from backtesting-framework.md harness); episodic analogs.
- **Writes:** `ResearchMemo` per candidate with `signal_block: {signals: [{name, value, validated_sharpe, last_validation_date}], factor_exposures: {...}, crowding_note: str}`.
- **Believability metrics:** fidelity (does memo match signal pipeline output? — audited automatically), incremental usefulness to PM decisions.
- **Failure modes & guards:** inventing signals or extrapolating beyond validation scope → guard: memo generator is template-constrained; any signal named must exist in the signal registry or the node fails.
- **Prompt anchors:** "You are a reporter of validated evidence, not an alpha improviser. If the library is silent on a name, say 'no validated signal' — that sentence is a fully acceptable output."
- **Cannot:** introduce signals not in the registry; override signal values.

### 3.4 TECH-01 — Technical Analyst
- **Pool/Tier:** Research / T1.5 (cheap T2 or strong T1; lowest-stakes memo)
- **Mission:** Describe price/volume structure: trend state, support/resistance, liquidity/ADV context, abnormal activity.
- **Reads:** OHLCV history and derived indicators for candidates. Nothing else.
- **Writes:** `ResearchMemo` with `technical_block: {trend: up|down|range, key_levels: [...], adv_pct_at_proposed_size: float, abnormal_volume: bool}`.
- **Believability metrics:** level usefulness (were key levels respected within horizon?), calibration.
- **Failure modes & guards:** pattern pareidolia → guard: restricted vocabulary of allowed concepts (configured list); low weight prior in believability store until earned.
- **Prompt anchors:** "Plain description over prediction. Your most valuable output is honest liquidity context and levels, not forecasts."
- **Cannot:** make fundamental claims; its stance alone can never carry a candidate to debate (protocol rule, restated here).

### 3.5 SENT-01 — Sentiment & News Analyst
- **Pool/Tier:** Research / T2 (T1 pre-filtering pipeline feeds it)
- **Mission:** Summarize news flow, earnings-call tone, and positioning chatter for candidates; classify what is *new* information vs. already-priced narrative; flag event risk.
- **Reads:** Time-bounded news/filings/transcript index for candidates; T1-generated event digests; episodic memory of how similar news episodes resolved.
- **Writes:** `ResearchMemo` with `sentiment_block: {news_novelty: new_info|rehash|mixed, tone_trend: improving|deteriorating|stable, event_risk_next_10d: [{event, date}], crowding_anecdotes: [doc_id]}`.
- **Believability metrics:** novelty-call accuracy (did 'new info' names move more?), event-risk recall (did flagged events occur/matter?), calibration.
- **Failure modes & guards:** sentiment double-counting with price momentum → guard: explicitly instructed to classify novelty, not direction; headline hallucination → Verifier citation rule.
- **Prompt anchors:** "Your job is novelty detection, not cheerleading. 'This is already priced' is one of your highest-value sentences."
- **Cannot:** access price data (deliberate: keeps it orthogonal to TECH-01/QUANT-01).

---

## 4. Adversarial Pool

### 4.1 BULL-01 / BEAR-01 — Adversarial Researchers
- **Pool/Tier:** Adversarial / T2, **mandatory different model families from each other** (ADR-2)
- **Mission:** Construct the strongest honest case for (BULL) / against (BEAR) each debated candidate, attacking the other side's evidence and the research memos' weak claims.
- **Reads:** All ResearchMemos for the candidate (post-Verifier), opponent's prior turns, episodic memory of similar setups. Bear additionally receives the fund's current exposure to correlated names (so its risk case is portfolio-aware).
- **Writes:** `DebateTurn` per round; final `closing_statement` with its 3 strongest surviving points.
- **Believability metrics:** scored by T3 Judge on evidence quality (not eloquence); long-run: did debates where this agent 'won' produce better trades? Bear has a dedicated metric: loss-avoidance value of vetoed/downsized trades.
- **Failure modes & guards:** **capitulation/sycophancy** (the #1 risk per research.md §II) → guard: role-locked prompts — these agents are *structurally forbidden from agreeing* with the opposite stance; concessions are allowed on individual points but the closing statement must argue their side at full strength regardless. Eloquence-over-evidence → guard: Judge scores cite-density and attack-relevance, order randomized.
- **Prompt anchors (Bear):** "You are the fund's immune system. You cannot capitulate. If the long case is strong, your job is to find the price, scenario, or crowding condition under which it still fails — there always is one."
- **Prompt anchors (Bull):** symmetric.
- **Cannot:** propose sizes; introduce uncited facts; declare a winner.

### 4.2 MOD-01 — Debate Moderator
- **Pool/Tier:** Adversarial / T2 (different family from both debaters where feasible)
- **Mission:** Enforce debate structure: round limits, concession requirements, claim/attack mapping; then extract the **pre-mortem** and a neutral disagreement summary.
- **Reads:** Memos + live transcript. No memory, no market data — it referees arguments, it doesn't have a view.
- **Writes:** `debate_summary: {resolved_points: [...], unresolved_cruxes: [...], premortem: {failure_scenarios: [{scenario, early_warning_indicator}]}, process_flags: [rule_violations]}`.
- **Believability metrics:** crux quality (were 'unresolved cruxes' what actually decided the outcome?), pre-mortem recall (when trades failed, had the pre-mortem named the scenario?).
- **Failure modes & guards:** drifting into having an opinion → guard: schema has no stance field; any directional language in summaries is flagged by Judge.
- **Prompt anchors:** "You have no view on the stock and never will. Your product is the *map of the disagreement* and the pre-mortem. A pre-mortem without observable early-warning indicators is unfinished."
- **Cannot:** vote; score the debate (that's the Judge); see believability weights.

---

## 5. Decision Pool

### 5.1 PM-01 — Portfolio Manager
- **Pool/Tier:** Decision / T2 (third model family where feasible — distinct from both debaters)
- **Mission:** Synthesize memos, debate summary, ballot result, episodic analogs, and portfolio context into sized `TradeProposal`s — or explicit NO-TRADE decisions with reasons.
- **Reads:** Everything in the cycle state for the candidate (post-Verifier), unsealed ballot, current portfolio/exposures, episodic memory analogs, semantic memory lessons, Macro memo.
- **Writes:** `TradeProposal` (schema §2.3) or `no_trade: {ticker, reason, what_would_reopen: str}`. Every proposal must state `expected_edge_bps` ≥ configured multiple of estimated round-trip costs — a structural "is this worth doing at all" check.
- **Believability metrics:** realized risk-adjusted P&L of proposals vs. ballot-only baseline (does PM synthesis add value over the vote?); sizing skill (hit rate × payoff vs. size correlation); NO-TRADE quality (opportunity cost of passes).
- **Failure modes & guards:** overriding strong dissent silently → guard: if PM proposes against the weighted ballot direction, `ballot_summary.dissent` must contain an explicit rebuttal, and these overrides are tracked as a dedicated believability sub-metric; size creep → guard: gate clamps are logged as PM calibration errors, training pressure toward realistic sizing.
- **Prompt anchors:** "You are graded on what happened after you decided, including the trades you didn't make. Conviction without invalidation conditions is not conviction; it's exposure. When the Bear's crux is unresolved, size like it."
- **Cannot:** submit orders; alter stops post-approval outside the deep loop; see raw debate transcript (only the Moderator summary + Judge scores — keeps eloquence from leaking into decisions).

### 5.2 EXEC-01 — Execution Planner
- **Pool/Tier:** Decision / T1.5
- **Mission:** Turn approved proposals into an execution plan that respects liquidity: order type, slicing, participation caps, timing windows.
- **Reads:** Approved proposals, ADV/liquidity stats, spread history, calendar (open/close auctions, event dates).
- **Writes:** `execution_plan: {ticker, slices: [{window, type, max_participation_pct}], abort_conditions: [...]}`. The order manager (code) executes this plan; deviations are reconciliation errors.
- **Believability metrics:** implementation shortfall vs. arrival price; plan-realism rate (plans that completed without aborts).
- **Failure modes & guards:** over-clever scheduling → guard: allowed order-type vocabulary fixed in configuration.md; participation hard caps in the gate.
- **Cannot:** change direction or size; trade names without an approved proposal.

---

## 6. Governance Pool

### 6.1 RISKA-01 — Risk Analyst (advisory; the binding gate is code — ADR-4)
- **Pool/Tier:** Governance / T2
- **Mission:** Write the risk narrative the code gate can't: correlation concentration in plain sight, crowding, regime mismatch, scenario losses, "what does the book look like if the Macro memo is wrong."
- **Reads:** Full proposed book (current + proposed), factor exposures, Macro memo, debate pre-mortems, stress scenarios from semantic memory.
- **Writes:** `risk_opinion: {trade_id, recommendation: proceed|downsize|reject, scenario_losses: [{scenario, est_pct_nav}], portfolio_interactions: [str], confidence}`. The PM must attach this to the proposal before the gate runs; a `reject` recommendation that the PM proceeds past requires written rebuttal (logged, tracked).
- **Believability metrics:** scenario realism (did flagged scenarios materialize at estimated magnitudes?), downsize value-add (P&L of heeded vs. overridden recommendations).
- **Failure modes & guards:** rubber-stamping → guard: a minimum rate of substantive findings is monitored; an opinion with zero portfolio_interactions on a correlated book is flagged. Crying wolf → its believability weight handles this naturally.
- **Prompt anchors:** "The gate checks limits; you check *judgment*. Your nightmare is ten approved trades that are secretly one trade."
- **Cannot:** block trades (code does); set limit values (configuration.md does).

### 6.2 COMP-01 — Compliance Agent
- **Pool/Tier:** Governance / T1
- **Mission:** Check proposals against mandate constraints: restricted list, universe membership, position-type permissions, wash-trade patterns vs. recent activity.
- **Reads:** Proposals, mandate config, restricted list, recent order history.
- **Writes:** `compliance_check: {trade_id, status: clear|violation, rule_refs: [...]}` — consumed by the gate as one of its inputs (violations are binding because the *gate* enforces them).
- **Failure modes & guards:** false negatives → rules are mirrored as code checks where expressible; the agent exists for fuzzy/pattern checks code can't express.
- **Cannot:** waive rules.

### 6.3 PMORT-01 — Post-Mortem / Attribution Agent
- **Pool/Tier:** Governance / T3 (judge family)
- **Mission:** Within minutes of every trade close: was the thesis right, wrong, or right-for-the-wrong-reasons? Skill or luck? What is the *one* transferable lesson, if any?
- **Reads:** Full trade record (thesis, memos, debate, ballot, proposal, fills, price path, pre-mortem), benchmark counterfactuals (e.g., sector ETF over same window).
- **Writes:** `post_mortem: {trade_id, outcome_vs_thesis: confirmed|refuted|unrelated_path, luck_skill_assessment: str, premortem_hit: bool, lesson: {text, generalizable: bool, tags}, agent_grades: {agent_id: contribution_note}}`. Feeds episodic memory directly; `generalizable: true` lessons enter the semantic-memory promotion queue (memory-systems.md).
- **Believability metrics:** lesson durability (do promoted lessons keep adding value?), grade fairness (audited by Meta-Agent sampling).
- **Failure modes & guards:** hindsight bias dressed as insight → guard: must explicitly answer "was this knowable at decision_ts, citing only documents available then?"; outcome bias → required to grade *process* and *outcome* separately.
- **Prompt anchors:** "A profitable trade with a refuted thesis is a loss that paid. Say so."
- **Cannot:** modify believability weights directly (code computes them from outcomes; PMORT provides annotations only).

### 6.4 META-01 — Meta-Agent (process improver, human-gated)
- **Pool/Tier:** Governance / T3, runs weekly, not per-cycle
- **Mission:** Mine the event log for *process* failures — systematic memo blind spots, debate degeneration, sycophancy drift (debate vs. independent-ensemble divergence), cost waste — and propose prompt/protocol/config changes.
- **Reads:** Event log aggregates, believability trends, sycophancy dashboard, cost dashboard, post-mortem corpus.
- **Writes:** `change_proposal: {target: prompt|protocol|config, diff, evidence, expected_effect, rollback_plan}` → human approval queue (architecture.md §10). Approved changes deploy with a new version stamp; effects are measured against the proposal's own `expected_effect`.
- **Believability metrics:** proposal hit rate (did approved changes deliver the expected effect?).
- **Failure modes & guards:** self-serving optimization / reward hacking → guard: cannot propose changes to the believability computation, the gate, the breakers, or its own approval process — those are constitutionally frozen (only the human may amend them).
- **Cannot:** deploy anything; touch L5; edit its own spec.

### 6.5 VERIF-01 — Claim Verifier & Debate Judge
- **Pool/Tier:** Governance(service) / T3, **different family from the agents it judges** (ADR-2)
- **Mission:** (a) Verify every memo claim against its cited documents — strip or flag unsupported claims before downstream consumption; (b) score debates on evidence quality with position randomized.
- **Reads:** Memos + cited L1 documents; debate transcripts (shuffled, role-masked where feasible).
- **Writes:** `verification: {claim_ref, status: supported|unsupported|misquoted}`; `debate_scores: {bull: {evidence, attack_relevance, concession_honesty}, bear: {...}}`.
- **Believability metrics:** audit agreement rate (human spot-checks), false-strip rate.
- **Failure modes & guards:** verbosity/position bias (LLM-judge literature) → randomized order, role masking, rubric-constrained scoring; over-stripping inference → claims typed `inference`/`estimate` are graded for reasonableness, not literal citation.
- **Cannot:** judge content from its own model family where an alternative exists; see ballot or believability data.

---

## 7. Roster Summary & Build Order

| ID | Pool | Tier | Phase introduced |
|---|---|---|---|
| MACRO-01 | Research | T2 | 2 |
| FUND-TECH (pilot sector) | Research | T2 | 1 |
| FUND-{others} | Research | T2 | 2 |
| QUANT-01 | Research | T2 | 2 (needs signal registry) |
| TECH-01 | Research | T1.5 | 1 |
| SENT-01 | Research | T2 | 1 |
| BULL-01 / BEAR-01 | Adversarial | T2 (different families) | 1 |
| MOD-01 | Adversarial | T2 | 1 |
| PM-01 | Decision | T2 (third family) | 1 |
| EXEC-01 | Decision | T1.5 | 2 (Phase 1 uses simple market/limit rules) |
| RISKA-01 | Governance | T2 | 2 (Phase 1: gate only) |
| COMP-01 | Governance | T1 | 2 |
| PMORT-01 | Governance | T3 | 1 (the learning loop must exist from day one) |
| META-01 | Governance | T3 | 3 |
| VERIF-01 | Governance | T3 | 1 |

Phase-1 minimum viable roster (8 agents): FUND-TECH, TECH-01, SENT-01, BULL-01, BEAR-01, MOD-01, PM-01, PMORT-01, with VERIF-01 as the integrity service — matching implementation-plan.md's MVP debate pipeline.

## 8. Open Items (deferred)
- Exact ballot mechanics and weight formula → decision-protocols.md
- Numeric thresholds referenced here (edge multiple, participation caps, round limits) → configuration.md
- Memory retrieval counts/recency windows per agent → memory-systems.md
- Prompt texts themselves → versioned implementation artifacts, reviewed against these anchors
