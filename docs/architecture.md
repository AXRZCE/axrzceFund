# architecture.md — System Architecture for the Multi-Agent AI Hedge Fund (US Equities, Paper Trading)

**Status:** v1.0 — Foundation document
**Depends on:** research.md (rationale and evidence behind every choice here)
**Feeds into:** agent-specifications.md, decision-protocols.md, configuration.md, implementation-plan.md

---

## 1. Purpose and Scope

This document defines the system topology, layers, orchestration model, LLM strategy, state model, communication patterns, and enforcement boundaries of the fund. It answers: *what talks to what, where state lives, what is enforced in code vs. reasoned by LLMs, and how the daily and intraday loops coexist.*

It deliberately does **not** contain: per-agent prompts and I/O contracts (agent-specifications.md), step-by-step workflow rules (decision-protocols.md), tunable parameter values (configuration.md), or validation math (backtesting-framework.md).

---

## 2. Architectural Principles (non-negotiable)

These principles resolve any design dispute that arises later. When in doubt, the principle wins.

1. **Auditability over convenience.** Every agent output, debate turn, vote, veto, order, and fill is written to an append-only event log before the next step may proceed. If it isn't logged, it didn't happen.
2. **LLMs reason; code enforces.** No risk limit, position cap, or drawdown circuit-breaker is ever implemented as a prompt instruction. All hard constraints live in deterministic code that LLM agents cannot override, persuade, or route around. (Research basis: un-overridable Millennium-style breakers; LLM sycophancy/jailbreak risk.)
3. **Independence before interaction.** Agents produce first-pass views in isolation before seeing any peer output. Debate happens only after independent positions are locked and logged. (Anti-sycophancy: research.md §II.)
4. **Heterogeneity by design.** Debating agents must run on different base model families wherever the debate's outcome matters. One model family with five role names is one detector with five labels.
5. **Point-in-time everything.** Every data record carries an `as_of` (event time) and `available_at` (knowledge time) timestamp. No component may read data with `available_at` later than the decision timestamp. This single rule kills most look-ahead bias at the architecture level.
6. **Cost tiering.** Cheap/fast models do retrieval, summarization, extraction, and monitoring. Expensive frontier models are reserved for debate, synthesis, and final decisions. Every LLM call is metered and attributed to an agent and a decision.
7. **Fail closed.** Any component failure, timeout, or unparseable output halts the affected trade pipeline in a NO-TRADE state. The system never "best-guesses" its way to an order.
8. **Everything is replayable.** Given the event log and the point-in-time data store, any past decision can be reconstructed exactly — including which model version and prompt version produced it.

---

## 3. System Topology — Seven Layers

```
┌─────────────────────────────────────────────────────────────────┐
│ L7  OBSERVABILITY        dashboards, metrics, cost meter, alerts │
├─────────────────────────────────────────────────────────────────┤
│ L6  EXECUTION            broker adapters (Alpaca/IBKR paper),    │
│                          order manager, fill reconciliation      │
├─────────────────────────────────────────────────────────────────┤
│ L5  ENFORCEMENT (CODE)   pre-trade risk gate, drawdown breakers, │
│                          position/exposure caps, kill switch     │
├─────────────────────────────────────────────────────────────────┤
│ L4  ORCHESTRATION        LangGraph state machines:               │
│                          Daily Deep Loop + Intraday Light Loop   │
├─────────────────────────────────────────────────────────────────┤
│ L3  AGENTS (LLM)         research / adversarial / decision /     │
│                          governance agent pools                  │
├─────────────────────────────────────────────────────────────────┤
│ L2  KNOWLEDGE & MEMORY   episodic memory, semantic memory,       │
│                          believability store, event log          │
├─────────────────────────────────────────────────────────────────┤
│ L1  DATA                 point-in-time market/fundamental/news   │
│                          store, ingestion pipelines, RAG indexes │
└─────────────────────────────────────────────────────────────────┘
```

Dependencies point downward only: agents read from L1–L2 and write proposals upward through L4; only L5 may submit to L6. Nothing in L3 can reach L6 directly — this is the most important arrow that does *not* exist in the diagram.

### L1 — Data Layer
- **Sources:** market data (Polygon or Alpaca data API), fundamentals (point-in-time provider), news and SEC filings (EDGAR + news API), corporate actions, delisted-stock history.
- **Point-in-time store:** a single canonical store (start: DuckDB/Parquet on disk; later: Postgres + object storage) where every row has `as_of` (event time) and `available_at` (knowledge time). PIT discipline is enforced through three independent layers:
  1. **Read filter (every query):** `WHERE available_at <= as_known_at`. Future rows are silently excluded; a backtest query at a historical date works correctly even when the store holds years of newer data. No exception is raised on historical queries.
  2. **Write guard (every ingest):** rows with `available_at > now()` are rejected at insert time. A row claiming to be knowable in the future is always a data bug (timezone error, vendor mislabel) — caught at the door.
  3. **Nightly audit (`audit_future_data()`):** independent scan for `available_at > now()` across all tables. Should be silent in steady state; fires only if the write guard was bypassed or data predates it. Distinct from the read filter — auditing for `available_at > as_known_at` would fire constantly on healthy historical data and is not the error condition being detected.
  > **Why three layers, not one:** conflating "serve only knowable data" (read concern) with "detect corrupt timestamps" (integrity concern) leads to a store that refuses every historical backtest query once any newer data is loaded. Keep them separate.
  > **Canonical-UTC invariant:** all three comparisons are string comparisons on TEXT timestamp columns, so every timestamp is normalized to canonical UTC (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) at the read/write boundary. This makes lexicographic order == chronological order. Without it a row stamped in a non-UTC offset (e.g. `…15:00:00-04:00` = 19:00 UTC) sorts as if it were 15:00 and defeats both the read filter and the write guard.
- **RAG indexes:** filings, transcripts, and news are chunked and embedded into a vector index, partitioned by date so retrieval can also be time-bounded.
- **Universe service:** maintains the investable universe (e.g., S&P 500 / Russell 1000 constituents *as of each historical date*, including delisted names) to avoid survivorship bias.

### L2 — Knowledge & Memory Layer
Three stores plus the log, all designed in memory-systems.md; the architecture fixes their roles:
- **Episodic memory:** every closed trade's full record — thesis, debate transcript, votes, sizing, outcome, post-mortem lesson. Retrieved by similarity (embedding of the current setup) at decision time.
- **Semantic memory:** validated, durable knowledge — signals that passed validation, lessons promoted from repeated post-mortems, regime playbooks. Shared fund-wide (Renaissance single-model principle).
- **Believability store:** per-agent, per-domain track records — calibration (Brier score), hit rate, realized risk-adjusted contribution of recommendations. Recomputed after every closed trade; consumed by the voting mechanism. No human or agent can hand-edit weights.
- **Event log:** append-only, ordered record of every system event (the audit backbone). Architecturally this is the source of truth; the other stores are derived views and can be rebuilt from it.

### L3 — Agent Layer (four pools)
Roles are specified in agent-specifications.md; the architecture fixes the pools and their permissions:

| Pool | Agents | May read | May write |
|---|---|---|---|
| Research | Macro, Sector Fundamental ×N, Quant, Technical, Sentiment/News | L1, L2 (read-only) | Structured memos to shared state |
| Adversarial | Bull, Bear, Debate Moderator | Memos + L2 | Debate transcripts, pre-mortems |
| Decision | Portfolio Manager, Execution Planner | Everything above | Trade proposals (never orders) |
| Governance | Risk Analyst (advisory), Compliance, Post-Mortem, Meta-Agent | Everything incl. event log | Risk opinions, attributions, *proposed* prompt changes (human-gated) |

Note the deliberate split: the **Risk Analyst agent** (L3) writes risk *opinions* that inform the PM; the **risk gate** (L5) is code and holds the actual veto. An LLM may recommend rejecting a trade; only code can physically block or pass one.

### L4 — Orchestration Layer
LangGraph state machines (recommendation and rationale in §4) implementing two loops (§6) plus housekeeping jobs (memory consolidation, believability recompute, nightly reconciliation).

### L5 — Enforcement Layer (deterministic code only)
- **Pre-trade risk gate:** checks every proposal against position limits, gross/net exposure, sector concentration, liquidity (ADV %), and factor-exposure caps from configuration.md. Pure functions, unit-tested, no LLM in the path.
- **Drawdown circuit-breakers:** Millennium-style automatic de-risking (e.g., halve at −X%, halt at −Y% — values in configuration.md) at pod and fund level, evaluated continuously by the intraday loop.
- **Kill switch:** human-operated and watchdog-operated global halt that cancels open orders and freezes the pipeline in a safe state.

### L6 — Execution Layer
- **Broker adapters:** a thin `BrokerInterface` with two implementations from day one — Alpaca paper and IBKR paper — so no broker quirk leaks into upper layers.
- **Order manager:** translates approved proposals into orders (slicing per the Execution Planner's plan), tracks order state, reconciles fills against intent, and writes everything to the event log.

### L7 — Observability Layer
- Structured logs and traces for every LLM call (model, tokens, cost, latency, prompt version).
- Dashboards: fund P&L/exposures, per-agent believability trends, debate-vs-independent-ensemble divergence (sycophancy early-warning), cost per decision.
- Alerting: breaker trips, reconciliation mismatches, data staleness, cost budget overruns.

---

## 4. Orchestration Framework — Recommendation: LangGraph

**Recommendation: LangGraph**, with a thin internal abstraction so graphs are defined in our own terms and LangGraph remains swappable.

**Why LangGraph over the alternatives:**
- **Explicit state graphs match the domain.** Our workflows are *deterministic pipelines with LLM-powered nodes* (memo → debate → ballot → decision → gate → order), not open-ended conversations. LangGraph's typed shared state, conditional edges, and checkpointing map 1:1 onto decision-protocols.md.
- **Auditability and replay.** Checkpointed state at every node transition gives us the replayability principle nearly for free; a crashed run resumes from the last checkpoint instead of re-spending LLM calls.
- **Human-in-the-loop primitives** (interrupts) fit our human gates (meta-agent change approval, kill switch).
- **CrewAI rejected** for core flows: role-based autonomous delegation is exactly the *lack* of control we're designing against; debate order, round limits, and ballot secrecy must be structural, not emergent.
- **Pure custom orchestrator rejected** for now: we'd re-implement checkpointing, retries, and tracing. The abstraction layer keeps this door open if LangGraph becomes a constraint in Phase 3+.

**Boundary rule:** LangGraph orchestrates L3–L4 only. The L5 enforcement layer is plain Python invoked *by* graph nodes but implemented and tested as an independent library with no LangGraph or LLM dependency.

---

## 5. LLM Strategy — Heterogeneous, Cost-Tiered

Three capability tiers; concrete model names and prices live in configuration.md so they can be swapped without touching architecture.

| Tier | Purpose | Profile | Heterogeneity rule |
|---|---|---|---|
| T1 Fast | Retrieval, extraction, summarization, intraday monitoring, formatting | Cheapest viable (e.g., small Claude / GPT-mini / Gemini Flash class) | Any single family is fine |
| T2 Reasoning | Research memos, bull/bear debate, PM synthesis, risk opinions | Frontier class | **Debating opponents must be different families**; PM a third where feasible |
| T3 Judge/Verify | Claim verification, debate scoring, post-mortems, meta-agent | Frontier class, different family from the agents it judges where possible | Judge ≠ judged |

Cost-control mechanisms built into the architecture (not left to discipline):
- **Budget governor:** a per-day and per-decision token/cost budget enforced at the orchestration layer; exceeding it degrades gracefully (fewer debate rounds, smaller candidate set) rather than silently overspending.
- **Memo caching:** research memos are content-addressed and reused within their validity window (e.g., a 10-K analysis is valid until the next filing) instead of regenerated.
- **Escalation, not default:** intraday and screening work runs on T1; T2 is invoked only when a screen, trigger, or disagreement justifies it ("debate only when necessary" — research.md §II).
- **Per-call metering:** every call logs model, tokens, dollars, agent, and decision ID, so cost-per-decision is a first-class dashboard metric.

---

## 6. Dual-Cadence Design — Daily Deep Loop + Intraday Light Loop

Both cadences exist from day one, but they are **not symmetrical**. Full multi-agent debate is too slow and too expensive to run per-tick; the evidence (research.md §VIII) also says LLM judgment adds most value at research/synthesis horizons, not high-frequency prediction. So:

### 6.1 Daily Deep Loop (the fund's brain) — runs after close + pre-open
1. Data refresh and universe screen (T1 agents + quant filters) → candidate list.
2. Independent research memos on candidates (Research pool, parallel, isolated).
3. Bull/Bear adversarial debate with Moderator on surviving candidates.
4. Secret-ballot, believability-weighted vote.
5. PM synthesis → sized trade proposals with thesis, catalysts, invalidation conditions, pre-mortem.
6. Risk Analyst opinion → **code risk gate** → approved order plan for the next session.
7. Post-mortems on trades closed that day → memory + believability updates.

### 6.2 Intraday Light Loop (the fund's reflexes) — runs continuously during market hours
Quant/code-dominated, T1-assisted, **no debate**:
- Executes the day's approved order plan (slicing, limit management).
- Monitors positions against each trade's pre-declared **invalidation conditions** and stop levels — exits require no new LLM decision because the exit logic was decided in the deep loop.
- Continuously evaluates drawdown breakers and exposure caps (L5).
- Watches news/halts/volatility for held names (T1 triage). A material event triggers either a pre-authorized de-risk action (defined per-trade in the deep loop) or an **escalation**: an emergency mini-graph (one T2 analyst + risk opinion + code gate) whose only allowed outputs are *reduce, hedge, exit, or hold* — never initiate new positions intraday in Phases 1–2.

This split keeps intraday latency and cost low, keeps the system honest about where LLMs add value, and still gives 24/7-style reflexes humans can't match. Intraday *alpha* strategies, if ever added, enter as validated quant signals in L1/L5 territory — not as intraday LLM debates.

---

## 7. State Model

### 7.1 Global Research State (per daily cycle)
A single typed object owned by the orchestrator, checkpointed at every node transition:
- `cycle_id`, `decision_ts` (the point-in-time boundary for all data reads)
- `universe_snapshot`, `candidates[]`
- `memos{agent_id → memo}` (structured, schema in agent-specifications.md)
- `debates{ticker → transcript, premortem}`
- `ballots{ticker → sealed votes}` (unsealed only after all votes are in)
- `proposals[]`, `risk_opinions[]`, `gate_results[]`, `approved_orders[]`
- `costs{agent_id → tokens, dollars}`

### 7.2 Trade Lifecycle (every trade is a state machine)
```
IDEA → RESEARCHED → DEBATED → VOTED → PROPOSED → RISK_GATED
     → APPROVED | REJECTED(terminal, with reason)
APPROVED → WORKING → FILLED → MONITORED
MONITORED → EXIT_TRIGGERED → CLOSING → CLOSED → POST_MORTEM(terminal)
(any state) → HALTED via kill switch / breaker
```
Transitions are emitted to the event log with the full causing context. A trade can never skip RISK_GATED, and nothing transitions to WORKING except via the L5 gate.

### 7.3 Identifiers and versioning
Every artifact carries: `trade_id`, `cycle_id`, `agent_id`, `model_version`, `prompt_version`, `config_version`. This tuple is what makes "replay any decision exactly" possible and lets the believability store attribute outcomes to the *version* of an agent that produced them.

---

## 8. Communication Patterns

1. **Structured memos to shared state (default).** Agents never message each other directly. They write typed memos (claims, evidence with citations to L1 documents, direction, confidence) into the research state. This avoids the long-chat "telephone effect" and makes every input to a decision inspectable.
2. **Bounded natural-language debate (exception, by design).** Only the Bull/Bear/Moderator subgraph uses free-form turns, with a hard round limit; the transcript is stored verbatim and then *summarized into structure* by a T3 judge before anyone votes.
3. **Sealed ballots.** Votes are written encrypted/withheld to state and revealed simultaneously; no agent sees another's vote before casting its own.
4. **Citation-or-it-didn't-happen.** Any factual claim in a memo or debate must reference a retrievable L1 document ID. The verifier rejects unsourced claims; rejected claims are excluded from PM synthesis. This is the architectural anti-hallucination mechanism.

---

## 9. Data Flow Walkthrough — One Trade, End to End

1. Nightly ingestion lands new prices/filings/news into the point-in-time store (`available_at` stamped on arrival).
2. Daily Deep Loop opens cycle `C`, fixes `decision_ts`, screens the universe → AAPL becomes a candidate.
3. Five research agents write independent memos on AAPL in parallel (T2, isolated, citing document IDs).
4. Bull and Bear debate over the memos; Moderator enforces rounds and extracts a pre-mortem ("this trade fails if …").
5. T3 judge scores the debate on evidence quality; sealed believability-weighted ballot follows.
6. PM synthesizes memos + debate + episodic memory of similar past setups → proposal: long AAPL, size S, thesis, catalysts, invalidation conditions, stop, horizon.
7. Risk Analyst writes an opinion; the **code gate** checks size, exposures, concentration, liquidity → APPROVED.
8. Order manager works the order next session via the broker adapter; fills reconciled; trade → MONITORED.
9. Intraday loop watches invalidation conditions, stops, and breakers daily; a pre-declared exit condition eventually fires → CLOSED.
10. Post-Mortem agent writes the outcome analysis (thesis right/wrong, luck vs. skill notes); episodic memory stores the full record; believability store updates every voting agent's weights; meta-agent ingests the lesson for its next (human-gated) improvement proposal.

Every numbered step above appended events to the log before the next began.

---

## 10. Enforcement Boundary — What Is Code vs. What Is LLM

| Concern | LLM (advisory) | Code (binding) |
|---|---|---|
| Idea generation, research, theses | ✅ | — |
| Debate, pre-mortems, synthesis | ✅ | round limits, ballot secrecy |
| Risk *assessment* narrative | ✅ Risk Analyst | — |
| Position limits, exposure caps, concentration, liquidity | proposes within | **enforces** |
| Drawdown circuit-breakers | — | **enforces, continuous** |
| Stops / invalidation exits | defines in deep loop | **executes intraday** |
| Order submission | plans slicing | **only path to broker** |
| Believability weights | — | **computed from outcomes** |
| Prompt/process changes | meta-agent proposes | human approves, versioned deploy |

If a future feature request requires an LLM on the right-hand column, the request is wrong.

---

## 11. Failure Isolation and Kill Behavior

- **Node-level:** LLM call failures retry with backoff, then fail the node → trade pipeline enters NO-TRADE for that candidate (fail closed). Unparseable outputs are failures, not warnings.
- **Loop-level:** if the Daily Deep Loop cannot complete, yesterday's approved plan does NOT roll over; the intraday loop manages exits only.
- **Data-level:** staleness checks gate every cycle; stale or gappy data for a name removes it from the candidate set and flags held positions for review.
- **Fund-level:** breaker trips and the kill switch cancel working orders, block new approvals, and (at the halt tier) flatten per the pre-defined de-risk policy. Recovery from HALTED requires human action — never automatic.
- **Watchdogs:** heartbeat monitors on both loops; a silent loop is treated as a failure, not as "quiet."

---

## 12. Deployment View (phased)

- **Phase 0–1:** single machine / single process. DuckDB + Parquet for L1, SQLite/JSONL event log, local vector index, LangGraph in-process, Alpaca paper. Optimize for iteration speed and replayability, not scale.
- **Phase 2:** split long-running services (ingestion, intraday loop, dashboards) from the daily batch graph; Postgres for the event log and stores; containerize.
- **Phase 3+:** queue-based agent workers if parallelism demands it; secrets management; multi-environment (research/replay vs. live-paper) separation.
The layer contracts (§3) are designed so this migration changes deployment, not architecture.

---

## 13. Architecture Decision Records (summary)

| # | Decision | Choice | Key rationale | Revisit when |
|---|---|---|---|---|
| ADR-1 | Orchestrator | LangGraph behind thin abstraction | deterministic graphs, checkpoints, replay | graph complexity or vendor friction |
| ADR-2 | LLM strategy | Heterogeneous, 3-tier cost model | debate diversity + cost control | model landscape shifts |
| ADR-3 | Cadence | Deep daily + light intraday; no intraday LLM entries | evidence on LLM value horizon; cost; latency | Phase 3, with validated intraday signals |
| ADR-4 | Risk enforcement | Code-only L5, LLM advisory split | sycophancy/override risk | never (principle) |
| ADR-5 | Source of truth | Append-only event log; stores are derived | audit + replay | never (principle) |
| ADR-6 | Data discipline | `as_of`/`available_at` on every row | look-ahead bias kill | never (principle) |
| ADR-7 | Initial storage | DuckDB/Parquet + SQLite, local | iteration speed | Phase 2 |
| ADR-8 | Broker | Alpaca paper primary, IBKR paper secondary, behind interface | API ergonomics; redundancy | live-capital discussion (far future) |

## 14. Open Questions (deferred, with owners)
- Exact memo/ballot schemas → agent-specifications.md
- Debate round limits, escalation thresholds, vote-weight formula → decision-protocols.md
- All numeric limits (breakers, caps, budgets) → configuration.md
- Memory consolidation and retrieval policies → memory-systems.md
- Post-cutoff testing windows and contamination controls → backtesting-framework.md
