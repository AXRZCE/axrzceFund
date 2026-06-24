# WP2 — Real agents vs post-cutoff golden-day fixtures: done-criteria + rulings

**Committed BEFORE implementation code** (brief §1.1), like WP1's seven.
**Branch:** `phase1/wp2-real-agents`.
**Binding specs (read-first, do not paraphrase):** `agent-specifications.md` §1 (universal
rules), §2 (schemas) + §3 (per-agent contracts/blocks) + §7 (roster/build order);
`decision-protocols.md` P2 (independent memo) + the VERIF-01 strip pass (P2 step 3);
`backtesting-framework.md` §2 (evidence classes) + §6 (LLM contamination controls — the
post-cutoff rule is **C1**); `validation-criteria.md` (schema-conformance + cost bars,
G1.2a/G1.2d/G1.2e).

**Goal:** replace the WP1 stubs with **real LLM agents**, each proven on **recorded historical
days that postdate the binding model training cutoff** — so there is no look-ahead and no
memorization. Build the integrity scaffolding (fixtures + gate + VERIF-01) with **zero LLM spend
first**; spend begins only at the first real agent (TECH-01).

> **Scope discipline (brief §4):** WP2 builds only the in-scope P2 research agents —
> **TECH-01, FUND-TECH, SENT-01** + the **VERIF-01** service + the fixture harness. No debate,
> ballot, PM, gate, or order path (those are WP3/WP4). MACRO-01 and QUANT-01 are OUT (Phase 2).

---

## Rulings (decided a priori — these are the bar; no post-hoc redefinition of "pass")

### R1 — Post-cutoff fixture gate (the hardest-to-fake proof). *[= backtesting §6 C1]*
The fixture loader **rejects any fixture whose trading date (`decision_ts`, the information
boundary) is at or before the training cutoff of the model that will read it.** Cutoff is
`cutoff(model_version)`, read from config, **keyed per model**; with heterogeneous models in a
run the **binding cutoff is the max** across all models in that run (backtesting §6 C1),
recorded per run. A deliberately **pre-cutoff fixture must be rejected**, proven by a test. **No
real LLM call runs against a fixture that has not passed this gate.** The gate is on the fixture's
information-boundary date, not its record date.

- *Grounding/consequence:* a post-cutoff fixture is what converts an otherwise-**E4 (banned,
  CONTAMINATED)** in-window agent backtest into **E1-like** validity (backtesting §2, §6). Every
  fixture-run decision record therefore carries an `evidence_class` label (post-cutoff ⇒ E1-like;
  the loader refuses to mint anything else for an agent run).
- *Recommended backstop (backtesting §6 C3, fold in if cheap):* a **memorization probe** before a
  run — elicit closing-price/headline recall for the fixture period; hit-rate above
  `⟨memorization_threshold⟩` disqualifies that model for that period. R1's date-gate is necessary;
  C3 is the tripwire that catches a model that memorized the window anyway. Date-gate is
  day-one-mandatory; C3 is build-if-cheap and flagged otherwise.

### R2 — All agent reads via `pit_store` as-of `decision_ts`.
No agent touches a vendor adapter or a raw file. **Every read goes through `data/pit_store.py`
with `as_known_at = decision_ts`** (brief §3 integration invariant; WP0's R5 boundary). A
**look-ahead audit over each fixture run is clean** — every read traced to `pit_store` with an
`as_known_at`/`available_at` ≤ `decision_ts`, zero future rows (the G0.2 / G1.1b standing
criterion, now exercised by agents). *This is where the WP1 `decision_ts`-in-the-replay-compare
fix goes load-bearing: the boundary that the replay protects is the same boundary every read is
clamped to.*

### R3 — Schema conformance enforced, not assumed.
Each memo is validated against the **§2.1 `ResearchMemo`** schema **plus the agent's §3 block**
(TECH-01 → `technical_block` §3.4; FUND-TECH → `valuation_block` §3.2; SENT-01 → `sentiment_block`
§3.5). The test **fails on drift**. Enforcement must add what the bare pydantic type does not:
- **VERIF-01 must demonstrably reject a *constructed bad* memo** — out-of-range `conviction`,
  missing `what_would_change_my_mind`, a wrong/extra field — not merely pass clean ones.
- **§2 cardinality/contract bounds the type alone misses:** `key_claims` 3–7 (§2.1), `thesis`
  ≤150 words (§2.1), `evidence: [doc_id]` non-empty for `claim_type: fact` (§1 rule 1 + P2 step 3).
- *Note from the §2 sweep (see `ballot-summary-reconcile-readout.md`):* §2 can lag the protocol
  specs, so the schema bar is built against §2.1 **as reconciled** + §3 blocks, not a remembered
  shape. The per-agent block is **mandatory** for that agent (a FUND memo without `valuation_block`
  is invalid by §3.2).

### R4 — Budget metering is real.
**Per-call token cost is recorded in the decision record** (input+output tokens and $ cost),
**non-zero and matching the actual call**, proven by a test — not a placeholder, not a constant.
Cost attaches to the artifact's replay tuple/event. (Feeds the G1.2d `cost per decision ≤ $8 p90`
bar; a metering that can't be gutted-to-red is the anti-hoax requirement.)

### R5 — Replay claim, honest framing (no fake "LLM determinism").
WP2 does **not** claim bit-exact LLM-output replay — LLMs are not deterministic. The replay tuple
captures **`prompt_version` + `model_version` + `decision_ts`** (+ the cycle's config/code
versions, per `core/replay.py`). The proof is twofold and bounded:
1. the **recorded** decision is **reconstructable from the event log** — replay reads the stored
   memo, it does **not** re-call the LLM; and
2. the **harness around the call is deterministic** — the same fixture + same stored memo yields
   the same VERIF-01 verdict, the same budget figure, the same schema result.

State this in code/tests so no one later builds a hoax "the LLM returned the same thing twice" test.

---

## Build order (data-only before interpretive; spend starts at TECH-01)
1. **`data/fixtures/` harness + R1 gate** — record real historical trading days (prices via SEP,
   fundamentals via SFA as-of; the SENT-01 source — see flag below) into replayable fixtures; the
   loader enforces R1. **Zero LLM spend.** Tested first (R1 rejection test).
2. **VERIF-01 service** — validates/strips memos per §2.1+§3 and P2 step 3. **Zero LLM spend** for
   its own validation logic (it judges claims against cited docs; the *judge model* call, if used,
   is metered like any agent). Tested with a constructed bad memo (R3).
3. **Research agents, one at a time, data-only first:** **TECH-01 → FUND-TECH → SENT-01.** Each: a
   real LLM call; a schema-valid `ResearchMemo` + its §3 block; reads **only** via `pit_store`;
   budget-metered; replay tuple stamped.

## Done — per agent, each demonstrable (not asserted)
For TECH-01, then FUND-TECH, then SENT-01:
- [ ] Produces a **schema-valid** memo (§2.1 + the agent's §3 block) on a **post-cutoff** fixture;
      test **fails on drift**.
- [ ] **VERIF-01 flags a constructed bad memo** for that agent's shape (not just clean passes).
- [ ] **Budget metering records real token cost** (non-zero, matches the call).
- [ ] **Look-ahead audit clean** — every read at `decision_ts` via `pit_store`, zero future rows.
- [ ] **Replay tuple** captures `prompt_version` + `model_version` (+ `decision_ts`); the decision
      record is reconstructable from the event log.

## Anti-hoax checks (the human audits against these — brief §0/§7)
- **The gutting test:** replacing an agent body with a **canned memo turns its test red.** The memo
  must be grounded in *that fixture's* data — a generic memo that ignores the fixture fails.
- **No canned returns outside `graphs/stubs/`.** As WP2 replaces a stub, that role leaves
  `graphs/stubs/`; a real agent that secretly returns a literal is a hoax, not a stub.
- **R1 gate cannot be bypassed:** the pre-cutoff-rejection test is the proof; an agent run that
  reaches an LLM on an ungated fixture is a failure.
- **Metering can't be faked:** a test asserts cost tracks the *actual* call, so a hardcoded cost
  goes red.
- Every artifact carries a `ReplayTuple`; every step emits its `Event`; hash-chain intact.

---

## Sequencing flags (raised now, not discovered mid-build)

- **SENT-01 has no point-in-time news source yet — its hard prerequisite.**
  `DocumentsInterface.get_news` is an **ABC with no concrete impl** (`data/interfaces/base.py:90`),
  and Sharadar (SEP/SF1) is prices+fundamentals, **not news**. SENT-01 reads a *time-bounded
  news/transcript index* (§3.5) and **cannot access price data** (§3.5 "Cannot"). So SENT-01 needs a
  concrete, **PIT-correct** `get_news` (as-of `decision_ts`, no look-ahead) or it breaks R2.
  **Decision:** build TECH-01 and FUND-TECH on the Sharadar data we already have; treat the news
  adapter as SENT-01's prerequisite. **If no PIT-correct news source is wireable, sequence SENT-01
  last and ship it flagged/deferred rather than fake sentiment** (faking it would violate R1/R2 and
  the anti-hoax contract). This is the one WP2 item that may not fully close; surface it, don't paper
  over it.

- **Post-cutoff window is real but finite.** Binding cutoff = max across the run's models. For
  Opus-class models the cutoff is ~Jan 2026, so usable fixture trading dates are ~Feb–Jun 2026
  (today is 2026-06-24). If TECH-01/FUND-TECH use cheaper T1/T1.5 tiers (per §7) with *different*
  cutoffs, each is keyed separately and the **max** binds. **Build prerequisite to verify at step 1:**
  a model→cutoff map exists in `configuration.md` (or add one); if absent, that is the first thing
  R1's gate needs and I will flag it before writing the loader.

- **Per-agent memo = base `ResearchMemo` + a typed §3 block.** The WP1 code carries only the base
  `ResearchMemo`. WP2 must extend it per agent (`technical_block`/`valuation_block`/`sentiment_block`)
  — the real schema-bar design point for R3. This is an additive schema build, not a §2 change.

## Standing rules carried from WP0/WP1 (unchanged)
Every load-bearing proof is a **committed, re-runnable test** (no deleted one-offs). Done-criteria
committed **before** code. WP ends with a readout in `docs/` + the events in `core/event_log.py`
(the event log is the source of truth). Branch + PR; **the human reads the PR — do not self-merge.**
