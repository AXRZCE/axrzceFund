# memory-systems.md — Episodic Memory, Semantic Memory, and the Believability Store

**Status:** v1.0 — Foundation document
**Depends on:** architecture.md (L2 layer, event log as source of truth), agent-specifications.md (who reads/writes what), decision-protocols.md (P2/P6/P9 touchpoints), configuration.md (§8 parameters)
**Feeds into:** implementation-plan.md (Phase 1 includes the minimum learning loop), monitoring-metrics.md (memory health metrics)

**Why this document exists:** the learning loop is the fund's compounding asset — the thing that makes trade #500 smarter than trade #5. It is also a contamination vector: a wrong "lesson" retrieved confidently is worse than no memory at all. This document designs both the learning and the immune system.

---

## 1. Principles

1. **Memory is a derived view.** The append-only event log is the source of truth (ADR-5); every store below can be dropped and rebuilt from it. Memory corruption is therefore always recoverable — and rebuild is a tested operation, not a theoretical one.
2. **Write is cheap, retrieval is curated.** We store everything; the design problem is what gets *surfaced* into an agent's precious context window, when, and with what framing.
3. **Lessons are hypotheses, not facts.** Anything entering semantic memory carries provenance, confirmation count, and a decay/review schedule. Memory never says "X is true"; it says "X was observed N times, last confirmed D, status: active|probation|retired."
4. **Memory must not become an anchor.** Retrieval injects *analogs and warnings*, never recommendations. Format and placement rules below exist to inform the new decision, not to rerun the old one.
5. **Agent-scoped views.** Each agent sees only the memory slice its spec allows (agent-specifications.md) — e.g., MOD-01 gets none; voting agents don't see believability data (including their own weights — knowing your weight invites gaming your calibration).

## 2. The Three Stores (and what they are not)

| Store | Contains | Analogy | Not |
|---|---|---|---|
| Episodic | Full per-trade records | a fund's deal files | a chat history |
| Semantic | Promoted, durable lessons & playbooks | the firm's institutional knowledge | a scratchpad for hunches |
| Believability | Per-agent, per-domain scored outcomes | Bridgewater baseball cards | editable by anyone |

Phase 1 implementation: episodic = SQLite/DuckDB tables + embeddings in the local vector index; semantic = small versioned YAML/DB table (it should stay *small* — see §4); believability = computed table, rebuilt nightly from the event log (never written directly).

## 3. Episodic Memory

### 3.1 Record schema (written by P9, one per closed trade; immutable)
```yaml
episode:
  trade_id, cycle_id, ticker, sector, direction
  setup_fingerprint:            # what similarity search runs over
    embedding: vec              # embedding of thesis + debate cruxes + regime label
    tags: [earnings_play, regime:risk_off, crowded_short, ...]
  decision_record: {memo_refs, debate_summary_ref, ballot, proposal_ref}
  outcome: {pnl_bps, holding_days, exit_reason, path_stats: {mae_bps, mfe_bps}}
  premortem_hit: bool
  post_mortem_ref               # PMORT-01 output incl. luck/skill assessment
  lesson_candidate: {text, generalizable: bool, tags} | null
```
Also written as episodes (Phase 2+): **material no-trades** — candidates that reached P6 and were passed on, with subsequent counterfactual return tracked. PM's "NO-TRADE quality" believability metric depends on these, and so does learning what we wrongly fear.

### 3.2 Retrieval policy (the curated part)
- **When:** P2 (research agents, for assigned candidates), P6 (PM), P3 (cautionary-flag check). Never during P4 debate (debaters argue from evidence, not precedent — prevents "we always lose on airlines" from becoming an argument) and never during P5 voting.
- **How:** top-`⟨episodic_retrieval_k⟩ = 5` by embedding similarity on `setup_fingerprint`, recency-weighted with `⟨recency_half_life⟩ = 180d`, with two slots reserved: at least one losing analog and at least one winning analog *if both exist* (forced balance — pure similarity tends to retrieve dramatic losses).
- **Injection format (anti-anchoring):** analogs render as a fixed-format box: setup summary, what happened, post-mortem one-liner, explicit banner: *"Analogs are context, not precedent. This trade is decided on its own evidence."* Outcomes shown in bps and holding days — no cumulative narratives.
- **Audit metric:** anchoring check — does memo stance correlate with retrieved-analog outcomes more than with current-evidence strength? (monitoring-metrics.md owns the test; META-01 reviews flags.)

## 4. Semantic Memory (small, slow, guarded)

### 4.1 What lives here
- **Lessons:** generalizable post-mortem findings that cleared promotion (§4.2). Format: `{lesson_id, text ≤ 50 words, tags, provenance: [episode_ids], confirmations, contradictions, status, next_review}`.
- **Regime playbooks:** MACRO-01-maintained summaries of how the book behaves per regime label (drawn from attribution data, not opinion).
- **Validated-signal cards:** mirrors of the Signal Registry entries QUANT-01 reports from (single source of truth remains the registry).

### 4.2 Lesson promotion pipeline (the immune system)
1. P9 emits `lesson_candidate` with `generalizable: true` → **probation queue**, status `probation`.
2. Promotion to `active` requires `⟨lesson_min_occurrences⟩ = 3` *independent* confirmations: episodes from different tickers and non-overlapping months whose post-mortems support the same lesson (PMORT-01 tags matches; code enforces independence rules).
3. Every active lesson carries `next_review` (default +90d): at review, contradiction count ≥ confirmation count since last review → demote to `probation`; two consecutive demotions → `retired` (kept, visible in history, no longer retrieved).
4. Contradiction tracking is automatic: when a trade matching a lesson's tags closes *against* the lesson's implication, a contradiction is logged — lessons are falsifiable by construction.
5. Hard cap: `⟨max_active_lessons⟩ = 40`. Beyond it, weakest-evidence lesson is demoted. A fund with 400 "lessons" has learned nothing; scarcity forces ranking.

### 4.3 Retrieval
Tag-matched lessons (max 3) injected into P6 PM context and matching P2 agents, rendered with confirmation counts and status — *"Lesson (active, 4 confirmations, last 2026-03):"* — so the PM can weigh evidence quality, not just obey.

---

## 5. Believability Store (the incorruptible track record)

### 5.1 What is scored (per agent, per domain)
- **Forecast records:** every memo stance and conviction becomes a scored forecast at its horizon (hit/miss vs. realized direction; Brier-scored calibration). Domains: sector × direction × regime, falling back to coarser buckets until `⟨min_observations_for_weighting⟩ = 25` is met at some granularity.
- **Vote records:** every ballot participation scored against trade outcome (and against counterfactual for no-trades, Phase 2+).
- **Role-specific metrics** from agent-specifications.md: MOD-01 premortem recall, BEAR-01 loss-avoidance value, PM override outcomes, RISKA heeded-vs-overridden differential, META-01 proposal hit rate.

### 5.2 Computation rules
- Rebuilt nightly from the event log by deterministic code. **No write API exists.** Not for humans, not for META-01 (Frozen Set §9.2). The only way to change a weight is to make better calls.
- Scores attach to the **version tuple** (agent_id, prompt_version, model_version): a major prompt or model change starts a linked-but-separate record — the old track record doesn't transfer wholesale (it informs a prior, discounted by `⟨version_carryover⟩ = 0.5`), because "same agent" after a model swap is a fiction.
- Displayed everywhere as score ± uncertainty (Wilson/bootstrap interval). The dashboard never shows a naked hit rate.

### 5.3 Consumption
- P5 weight formula (configuration §4) — Phase 3+, after the A/B experiment (backtesting-framework §7) justifies switching it on.
- META-01 reads aggregates for process mining; PMORT-01 annotates but cannot alter.
- Voting agents never see weights (theirs or others') — §1.5.

## 6. Memory Hygiene & Failure Modes

| Failure mode | Mechanism | Defense |
|---|---|---|
| Wrong lesson learned confidently | one dramatic episode generalized | probation + 3 independent confirmations + falsifiability tracking |
| Anchoring on analogs | similarity retrieval = self-fulfilling pattern | forced win/loss balance, anti-anchoring banner, anchoring audit metric, no retrieval in debate/voting |
| Memory bloat → context pollution | unbounded growth | max_active_lessons cap, k=5 episodic cap, ≤3 lessons in context |
| Outcome bias contaminating lessons | lucky trades minting "wisdom" | lessons cite post-mortem *process* assessment; luck-flagged episodes can't confirm lessons |
| Believability gaming | agents optimizing for the metric | agents can't see weights; calibration (Brier) punishes confidence games; version-tuple resets |
| Stale regime knowledge | 2024's lessons in 2027's market | recency half-life, lesson review cycle, regime-tagged retrieval |
| Store corruption / bad migration | derived-view bugs | nightly rebuild-from-log spot check on sampled records; full rebuild drill quarterly |

## 7. Lifecycle, Ops, and Audit
- **Consolidation job (nightly, after P10):** writes episodes for trades closed today, rescores believability, processes the probation queue, runs the anchoring audit, emits memory-health metrics (store sizes, retrieval latencies, lesson churn).
- **Replay compatibility:** retrieval calls are logged with their inputs and returned items (the replay tuple extends to memory: re-running a decision retrieves the *same* analogs from the archived state, not today's).
- **Privacy/scope note:** memory contains only market data, our own decisions, and model outputs — no personal data; still, the event log's hash chain covers memory tables to detect tampering.
- **Quarterly memory review (human + META-01):** read the active lesson list end to end (it's ≤40 items by design — readable in one sitting), retire anything that smells like curve-fit folklore, and review the anchoring audit trend.

## 8. Phase Mapping
- **Phase 1 (must exist from day one):** episodic writes + P9 loop, k=5 retrieval into P2/P6, believability *recording* (not weighting), probation queue. The learning loop is not a later feature; trade #1 must already be teaching trade #2.
- **Phase 2:** no-trade counterfactual episodes, regime playbooks, anchoring audit automation, full lesson review cycle.
- **Phase 3:** weighting switched on per the A/B gate; version-carryover machinery exercised by the first prompt-evolution wave (META-01).

## 9. Open Items
- Embedding model choice for setup_fingerprint (cheap + stable matters more than SOTA; pin the version — embedding drift silently breaks similarity) — Phase 1 build decision.
- Counterfactual window for no-trade scoring (candidate: memo horizon_days) — Phase 2.
- Whether debate summaries (not just cruxes) belong in the fingerprint — revisit after anchoring-audit data exists.
