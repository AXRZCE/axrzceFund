# decision-protocols.md — Operational Workflows, Debate Rules, and Decision Mechanics

**Status:** v1.0 — Foundation document
**Depends on:** research.md (evidence), architecture.md (loops, state, enforcement boundary), agent-specifications.md (roster, schemas)
**Feeds into:** configuration.md (every numeric named here gets its value there), monitoring-metrics.md (every protocol emits metrics)

---

## 0. Conventions

- Protocols are numbered **P1–P12**. Each defines: trigger, participants, steps, outputs, failure handling, and emitted metrics.
- Numbers written as `⟨name⟩` are **parameters** — their values live in configuration.md, not here. This document fixes the *logic*; configuration fixes the *knobs*.
- Every protocol step appends to the event log before the next step may run (architecture.md Principle 1).
- "Fail closed" means: on unrecoverable error, the affected candidate/trade enters NO-TRADE or exit-only state; the system never improvises past a failed step.

---

## P1 — Daily Cycle Open & Candidate Screening

**Trigger:** scheduled, post-close (primary run) with a pre-open refresh pass.
**Participants:** code screeners + T1 agents; QUANT signal pipeline.

1. Orchestrator opens cycle `C`, fixes `decision_ts`, verifies data freshness (staleness gate per name; stale names excluded and, if held, flagged to the intraday loop).
2. Universe service emits the point-in-time universe.
3. Screening funnel produces the candidate list:
   a. **Quant screen** (code): validated-signal triggers, liquidity floor `⟨min_adv_usd⟩`, price floor, borrow availability for shorts.
   b. **Event screen** (T1): names with new filings/earnings/material news since last cycle.
   c. **Held-position review:** every open position is automatically a candidate (re-underwriting is mandatory, not optional).
4. Candidate list capped at `⟨max_candidates_per_cycle⟩` by screen-score priority; cap exists for cost and attention-quality reasons.

**Outputs:** `candidates[]` with screen provenance (why each name is here).
**Failure handling:** screening failure aborts new-idea flow; held-position review must still complete (exit-management is never skipped).
**Metrics:** candidate count, screen-source mix, data-staleness exclusions.

---

## P2 — Independent Memo Phase (isolation enforced)

**Trigger:** P1 complete.
**Participants:** Research pool (per roster/phase), in parallel.

1. Each research agent receives **only** its specified reads (agent-specifications.md) for assigned candidates. No agent receives another's memo — enforced by the orchestrator's context assembly, not by prompt politeness.
2. Agents write `ResearchMemo`s. Schema violations → one retry with error feedback → node failure (candidate proceeds with that memo marked ABSENT; a candidate missing more than `⟨min_memos_required⟩` memos is dropped this cycle).
3. **VERIF-01 claim verification pass:** every `claim_type: fact` claim is checked against cited documents. `unsupported`/`misquoted` claims are stripped; a memo losing more than `⟨max_stripped_claims_pct⟩` of its claims is voided (treated as ABSENT) and logged as an agent-quality event.
4. **Independent baseline snapshot:** each memo's `stance` × `conviction` is recorded *now* as the agent's pre-debate position. This snapshot is the anti-sycophancy benchmark used in P4, P6, and the sycophancy dashboard.

**Outputs:** verified memos in cycle state; independence baseline.
**Metrics:** memo completion rate, strip rate per agent, time/cost per memo.

---

## P3 — Debate Eligibility Gate (debate only when necessary)

**Trigger:** P2 complete.
**Logic (code, not LLM):** a candidate goes to full adversarial debate only if it earns it:
- **Disagreement:** verified memos materially disagree (stance split, or conviction-weighted dispersion > `⟨debate_dispersion_threshold⟩`); or
- **Stakes:** proposed exposure would exceed `⟨debate_size_threshold_pct_nav⟩`, or the name is a new position (all new positions debate in Phases 1–2); or
- **Memory flag:** episodic memory retrieval surfaces a past similar setup that ended in a post-mortem lesson tagged `cautionary`.

Candidates with unanimous low-stakes agreement skip to P5 with an **ensemble-only** marker (research.md: much of debate's measured benefit is ensembling; we don't pay debate costs where there's nothing to debate). Held positions with no new information and no triggered conditions are summarily re-approved at current size ("no action" is the default state, and it's free).

**Metrics:** debate rate, skip reasons — these feed the Phase-3 evaluation of whether debate adds value over ensembling at all.

---

## P4 — Adversarial Debate Protocol

**Trigger:** candidate passes P3.
**Participants:** BULL-01, BEAR-01 (different model families), MOD-01; VERIF-01 scoring after.

1. **Round structure:** maximum `⟨max_debate_rounds⟩` rounds (default expectation: 3 — opening, rebuttal, closing). MOD-01 may end debate early if both sides' new-evidence rate hits zero, but may never extend past the cap.
2. **Turn rules (enforced by schema + Moderator):**
   - Every argument must cite evidence or explicitly attack a specific memo/opponent claim by reference.
   - From round 2: `concessions` must be non-empty and `steelman_of_opponent` is graded — refusing to acknowledge the opponent's best point is a process flag.
   - Closing statements must argue the agent's assigned side at full strength (capitulation = role violation → debate voided, re-run once with fresh instances; repeated violation is a META-01 escalation).
3. **Moderator extraction:** MOD-01 writes `debate_summary` — resolved points, **unresolved cruxes**, and the **pre-mortem** with observable early-warning indicators per failure scenario.
4. **Judge scoring:** VERIF-01 scores both sides on evidence quality, attack relevance, concession honesty — transcript order randomized, roles masked. Scores attach to the debate record (and feed believability), but **do not decide anything by themselves**.

**Outputs:** debate_summary + premortem + judge scores.
**Failure handling:** debater node failure → re-run once; second failure → candidate proceeds *without* debate but flagged `DEBATE_FAILED` — the PM may then propose at no more than `⟨undebated_size_cap_pct_nav⟩`.
**Metrics:** rounds used, early-stop rate, role-violation rate, judge score spreads, cost per debate.

---

## P5 — Sealed Believability-Weighted Ballot

**Trigger:** P4 complete (or P3 skip with ensemble-only marker).
**Voters:** all Research-pool agents that produced a valid memo for the candidate, plus BULL-01 and BEAR-01 (whose votes are constitutionally fixed to their roles and exist to carry their judge-scored strength into the record — see weighting). MOD-01, PM-01, governance agents do not vote.

1. **Sealed casting:** each voter receives the verified memos + debate_summary (not the raw transcript) and casts `{stance: long|short|no_position, conviction: 0–1, size_inclination: small|standard|high}`. Votes are written sealed; no voter sees another ballot before all are cast. Voting agents are *fresh instances* — they do not see their own P2 memo identity beyond its content, reducing self-anchoring.
2. **Unsealing & tally (code):** the weighted score for each direction is
   `score(d) = Σ_i w_i · conviction_i · 1[stance_i = d]`
   where agent weight `w_i` comes from the believability store:
   `w_i = clip( base · calib_i^⟨α⟩ · hit_i^⟨β⟩ · contrib_i^⟨γ⟩ , ⟨w_min⟩, ⟨w_max⟩ )`
   - `calib_i`: inverse-Brier calibration score (domain-specific where data allows: FUND-TECH's weight on tech names uses tech-name history).
   - `hit_i`: stance hit rate at memo horizon.
   - `contrib_i`: realized risk-adjusted contribution of trades this agent supported vs. opposed.
   - Exponents `⟨α,β,γ⟩` and clips are configuration; **Phase 1–2 runs with all weights equal** (`w_i = 1`) because weights without track records are noise — believability weighting activates in Phase 3 only after `⟨min_observations_for_weighting⟩` scored calls per agent.
   - **Sycophancy check (automatic):** each voter's ballot is compared to its P2 independent baseline. A stance flip *toward the debate's apparent winner* without new evidence cited is logged as a conformity event (dashboard metric; persistent flippers get a META-01 review).
3. **Ballot outcome:** direction with max score wins if `score_margin ≥ ⟨ballot_margin_threshold⟩`; otherwise outcome is CONTESTED.
   - **Margin definition (ruled 2026-07-01, WP3 R4-PRE — Akshar):** `score_margin` is **normalized**:
     `margin = (score_top − score_runner_up) / total_cast_weight`, where **total cast weight =
     Σ_i w_i·conviction_i over ALL ballots cast** (no_position included — an abstainer's weight
     dampens the margin rather than vanishing). *Rationale:* `contested` measures **disagreement
     among the voters**; the absolute strength of conviction is separately handled by P6's
     `conviction_factor` sizing, so the threshold must be scale-free across ballots of different
     sizes/conviction levels. *Motivating case:* the WP3-CP2 smoke ballot (long 1.15 vs short 0.67,
     total cast 2.55) reads margin **0.2637** under this rule (not contested), but **0.48**
     unnormalized and **0.16** (contested!) if normalized by voter count — three readings, three
     different contested outcomes; the spec previously never defined the denominator.
     `configuration.md` §4's "margin below 20% **of total cast weight**" is the same rule stated
     from the threshold side. Boundary: `margin == threshold` ⇒ **NOT** contested.

**Outputs:** `ballot_summary {weighted_score, margin, dissent_summary, contested: bool}`.
**Metrics:** margin distribution, conformity events, weight concentration (no agent's weight may exceed `⟨w_max⟩` — prevents a hot streak from becoming a dictatorship).

---

## P6 — PM Synthesis & Proposal

**Trigger:** P5 complete.
**Participant:** PM-01 (third model family).

1. PM receives: verified memos, debate_summary + premortem, judge scores, unsealed ballot, current portfolio state, episodic analogs, Macro regime memo, semantic-memory lessons matching the setup's tags.
2. PM decides per candidate: `TradeProposal` or `no_trade` (with `what_would_reopen`).
3. **Hard proposal rules (schema-enforced):**
   - `expected_edge_bps ≥ ⟨edge_to_cost_multiple⟩ ×` estimated round-trip cost, else the proposal is invalid.
   - Every proposal carries stop, invalidation conditions (machine-checkable where possible), horizon, and the pre-mortem's top risks.
   - CONTESTED ballots: proposal size capped at `⟨contested_size_cap_pct_nav⟩`.
   - **Override rule:** proposing *against* the ballot direction requires a written rebuttal addressing the majority's strongest crux; overrides are capped at `⟨max_overrides_per_month⟩` and tracked as a dedicated PM believability metric. (Dalio: override the weighted vote "only at your peril" — here the peril is measured.)
   - DEBATE_FAILED names: size ≤ `⟨undebated_size_cap_pct_nav⟩`.
4. **Sizing discipline:** size starts from a fractional-Kelly-inspired base `⟨base_size_pct_nav⟩ × conviction_factor`, then is reduced by each applicable haircut (contested, regime-mismatch flag from Macro, unresolved Bear crux, low liquidity). Sizing never increases through narrative enthusiasm — haircuts only multiply downward from base. Phase 3 may add conformal-confidence scaling (research.md Tier 1).

**Outputs:** proposals[] / no_trade[].
**Metrics:** proposal rate, override rate, average haircut stack, NO-TRADE reasons.

---

## P7 — Risk Opinion, Compliance, and the Code Gate

**Trigger:** P6 complete. **Order is fixed:** RISKA-01 → COMP-01 → gate. The gate is last and binding.

1. **RISKA-01** writes `risk_opinion` per proposal (portfolio-interaction narrative, scenario losses, proceed/downsize/reject). PM proceeding past a `reject` requires a logged rebuttal (same peril-tracking as ballot overrides).
2. **COMP-01** runs mandate checks → `compliance_check`.
3. **Code gate (L5)** evaluates, in order: compliance status → position limit `⟨max_position_pct_nav⟩` → sector cap `⟨max_sector_pct_nav⟩` → gross/net exposure `⟨max_gross⟩/⟨net_band⟩` → liquidity (size ≤ `⟨max_adv_participation_pct⟩` of ADV) → factor-exposure caps → current breaker state. First failure rejects with a machine-readable reason. The gate may also **clamp** size to the binding constraint instead of rejecting, if the clamp ratio ≥ `⟨min_clamp_ratio⟩` (a 5% trim is a clamp; a 60% trim means the proposal was wrong — reject).
4. Approved proposals + EXEC-01 plans (Phase 2+) become the next session's order plan.

**Failure handling:** gate code errors fail closed (reject). There is no human override of the gate mid-cycle; if a limit is wrong, the fix is a configuration.md change with its own approval protocol (P11).
**Metrics:** rejection/clamp rates by rule, RISKA recommendation-vs-outcome record.

---

## P8 — Intraday Monitoring & Escalation

**Trigger:** continuous during market hours (Intraday Light Loop).
**Participants:** code monitors + T1 triage; emergency mini-graph on escalation.

1. **Order working:** order manager executes plans; aborts on plan abort_conditions.
2. **Continuous code checks (every `⟨monitor_interval⟩`):** stops and machine-checkable invalidation conditions per trade; drawdown breakers (pod: −`⟨pod_halve_dd⟩` → halve, −`⟨pod_halt_dd⟩` → flatten pod; fund: −`⟨fund_derisk_dd⟩` → de-risk to `⟨derisk_gross⟩`, −`⟨fund_halt_dd⟩` → HALT); exposure drift re-checks.
3. **T1 news triage:** material-event classifier on held names. Events map to: (a) pre-authorized action from the trade's proposal (execute immediately), or (b) **escalation**.
4. **Escalation mini-graph (the only intraday LLM decision):** one T2 analyst memo (event-focused) + RISKA-01 opinion + code gate. Allowed outputs: `hold | reduce | hedge | exit`. **Never** new entries, never size increases, intraday (Phases 1–2). Must complete within `⟨escalation_timeout⟩` or default to `reduce ⟨default_derisk_pct⟩`.

**Metrics:** stop/invalidation trigger counts, escalation rate and latency, breaker proximity (distance-to-trip is a standing dashboard number, not a surprise).

---

## P9 — Post-Mortem & Learning Loop

**Trigger:** any trade reaches CLOSED; also weekly batch for open positions older than `⟨aging_review_days⟩`.

1. PMORT-01 writes the post_mortem (process vs. outcome graded separately; "knowable at decision_ts?" answered with citations).
2. Code updates: episodic memory write (full record); believability store recompute for every voter and the PM; pre-mortem hit/miss recorded for MOD-01.
3. Lessons tagged `generalizable: true` enter the semantic-memory promotion queue: promoted only after `⟨lesson_min_occurrences⟩` independent confirmations (memory-systems.md owns the mechanics).

**Metrics:** post-mortem latency, premortem hit rate, lesson promotion rate.

---

## P10 — Cycle Close & Reconciliation

Nightly, after P9: positions/fills reconciled against broker statements; event-log integrity check (hash chain); cost roll-up per decision; dashboard refresh; cycle `C` sealed (immutable thereafter).
**Failure handling:** reconciliation mismatch beyond `⟨recon_tolerance⟩` → next cycle opens in exit-only mode until resolved.

---

## P11 — Change Management (META-01 and humans)

1. META-01 emits `change_proposal`s weekly (architecture.md §10 boundary: never the gate, breakers, believability math, or its own approval path).
2. Human reviews → approve/reject. Approved changes deploy at the next cycle boundary with new `prompt_version`/`config_version`; never mid-cycle.
3. Every change runs as a **measured experiment**: the proposal's `expected_effect` is checked at `⟨change_review_horizon⟩`; failed predictions count against META-01's believability and are candidates for rollback (every change ships with its rollback plan).
4. Emergency config changes (e.g., a limit is discovered dangerously wrong) follow the same path compressed: human-initiated, logged with reason, flagged for retroactive review.

---

## P12 — Halt & Recovery

1. HALT sources: fund breaker, kill switch (human), watchdog (silent loop), reconciliation hard-fail, data-integrity alarm.
2. On HALT: cancel working orders → block approvals → execute the pre-defined de-risk policy for the halt tier → notify human.
3. **Recovery is always human-initiated** and follows a checklist: cause identified → fix deployed/verified → replay test on the failure window passes → human signs resume → system restarts in exit-only mode for `⟨cooldown_cycles⟩` cycles before new entries re-enable.

---

## Edge-Case Ledger (quick reference)

| Situation | Resolution | Protocol |
|---|---|---|
| Tie / thin ballot margin | CONTESTED → size cap or NO-TRADE | P5/P6 |
| PM wants to defy ballot | written rebuttal + capped frequency + tracked | P6 |
| RISKA says reject, PM proceeds | logged rebuttal, peril-tracked | P7 |
| Gate vs. anyone | gate wins, always | P7 |
| Debater capitulates | debate voided, one re-run, escalate pattern | P4 |
| Memo unparseable twice | memo ABSENT; too many ABSENT → candidate dropped | P2 |
| Debate node fails twice | DEBATE_FAILED → undebated size cap | P4 |
| Escalation times out | default de-risk action | P8 |
| Data stale for held name | flag to intraday, exit-only management | P1/P8 |
| Deep loop fails entirely | no rollover of yesterday's plan; exits only | architecture §11 |
| Reconciliation mismatch | exit-only mode until resolved | P10 |
| Agent on hot streak | weight clipped at ⟨w_max⟩ | P5 |
| New agent, no track record | weight = baseline; no weighting until min observations | P5 |

## Open Items
- All `⟨parameters⟩` → configuration.md (next document; every parameter named here must appear there with a value and a rationale).
- Sycophancy dashboard thresholds and alerting → monitoring-metrics.md.
- Lesson promotion mechanics → memory-systems.md.
