# WP5 — PMORT-01 + learning loop (capture only) + dashboard v1: done-criteria + rulings

**Committed BEFORE implementation code**, like WP1's seven, WP2's five, WP3's seven, WP4's seven.
**Branch:** `phase1/wp5-learning` (off verified merged `origin/main` = `330fdbb`, PR #6 in —
verified by CODE CONTENT: monitor/risk_gate/orders/costs present, pm.py placeholder-free, the wall
test spot-run green). **R-numbering:** per-WP (this is the **WP5 R-series, R1–R7**).

**Binding specs (read against fetched code):**
`decision-protocols.md` **P9** (:167–171 — PMORT-01 writes the post_mortem, *process vs. outcome
graded separately*, "knowable at decision_ts?" answered **with citations**; episodic write;
premortem hit/miss recorded; `generalizable: true` lessons → the promotion queue) and **P10**
(dashboard refresh at cycle close);
`agent-specifications.md` **§6.3** (:204–212 — PMORT-01, **T3 judge family**; the `post_mortem`
schema `{trade_id, outcome_vs_thesis: confirmed|refuted|unrelated_path, luck_skill_assessment,
premortem_hit, lesson{text, generalizable, tags}, agent_grades}`; guards: hindsight → the
knowable-at-decision_ts question; outcome bias → process/outcome separated; **Cannot: modify
believability weights** — code computes them, Phase 3);
`memory-systems.md` §1 (**memory is a derived view; the event log is the source of truth**), §3.1
(the immutable episode schema, incl. `outcome{pnl_bps, holding_days, exit_reason, path_stats}`;
material no-trades = Phase 2+ episodes), §3.2 (retrieval never during P4/P5; anti-anchoring
format), §4.2 (probation → promotion after `lesson_min_occurrences = 3` INDEPENDENT confirmations;
contradiction tracking; `max_active_lessons = 40`), §5 (believability: **no write API exists**,
rebuilt from the log — Phase 3);
`configuration.md` §8 (`aging_review_days = 30`, `lesson_min_occurrences = 3`,
`episodic_retrieval_k = 5`, `recency_half_life = 180d`);
**Plumbing to REUSE, not reinvent:** `core/heterogeneity.resolve_judge_family` +
`assert_judge_disjoint` (CP0) and the per-family T3 judge seats already in the manifest
(`VERIF-01-JUDGE-{GOOGLE,OPENAI,CHINESE}`) — PMORT-01 is T3 judge-family and seats through them;
`graphs/monitor.py` (breaker/stop events) + `graphs/orders.py` (modeled fills) are post-mortem
inputs; the WP3/WP4 smoke artifacts under `results/` are the real records the dashboard renders.

**Scope boundary (the plan's explicit rule):** outcome/lesson **CAPTURE ONLY**. Believability
weighting is **Phase 3** — no weights are built, stored, or consumed anywhere in WP5 (R3 pins this
with a red test).

---

## Data reality (stated up front — no faked outcomes, ever)

**Decision records that exist today (committed artifacts):**
| Record | Where | Contains |
|---|---|---|
| MDT trade decision (0.735%, stop $71.50, 400 bps edge claim, sizing audit, ballot) | `results/wp3_cp3/pm_smoke.json` | the primary post-mortem subject |
| MDT modeled order + fill (buy 91 @ 80.151027, 2026-06-25) | `results/wp4/replay_smoke.json` | the entry the outcome marks against |
| COST **no_trade** (+ judge scores, shadow votes, contested ballot) | `results/wp3_cp4/full_smoke.json` | the no-trade post-mortem subject (R6a) |
| AVGO debate/ballot (no PM stage) | `results/wp3_cp2/debate_smoke.json` | dashboard input only |
| HALT demo, gate audits, per-trade costs | `results/wp4/replay_smoke.json` | dashboard + monitor-event inputs |

**Outcome data that exists today: NONE.** Local SEP bars for the golden-day tickers end
**2026-06-24** (correcting the WP4-open cross-ticker impression: the post-06-26 bars belong to
AAPL/MSFT/NVDA from the Alpaca soak ingests — no decisions attached to those names). No stored
decision has a single post-decision mark.

**What honestly unlocks a REAL (not faked) partial outcome:** a targeted SEP backfill via the
EXISTING ingestion path (`ingest_sep(tickers=…)`, the WP2-A1 precedent) for MDT + COST covering
2026-06-25 → latest — $0 LLM, inside the Sharadar subscription. That yields real marks for the
stored MDT entry and the COST counterfactual. Even then the window is **PARTIAL** (~4–5 sessions
vs the proposal's horizon; `aging_review_days = 30` not reached): WP5 can prove an **INTERIM**
open-window post-mortem on real marks — never a closed-trade verdict.

**Provable NOW vs first-fires-at-WP6:**
- NOW: the capture/retrieval/dashboard machinery on stored records (all red-testable, $0); one
  real PMORT-01 call on the MDT decision with backfilled real marks, labeled INTERIM (the smoke).
- WP6+: the first CLOSED/stopped outcomes (a stop or invalidation closing a modeled position in
  the dry-run week); the P9 closed-trade trigger; promotion to `active` (needs 3 independent
  episodes — different tickers, non-overlapping months — arithmetically impossible before WP6+);
  the P10 nightly dashboard refresh cadence.

---

## Rulings (decided a priori; every ruling names a red test)

### R1 — PMORT-01 is family-disjoint from the decided family and GROUNDED in the record.
PMORT-01 produces a post-mortem for a closed/stopped/interim decision. Its family is resolved **at
call time** via the CP0 primitive (`resolve_judge_family(judged_family=PM-01's, available)`)
seating through the existing `VERIF-01-JUDGE-<family>` T3 manifest roles (no new slugs; the
ReplayTuple's `agent_id` records `PMORT-01`, `model_version` the seat's) — judged = the DECIDED
family (google/PM-01), so the resolver lands on a disjoint family; the call site asserts
disjointness (`assert_judge_disjoint`), the no-alternative case logged never silent. **Grounded:**
the post-mortem must cite facts that exist in the stored decision record + the outcome marks — a
canned post-mortem citing nothing from the record fails (the WP3-judge grounding pattern).
- **Red tests:** forced `family(PMORT) == family(PM-01)` with a disjoint family available → raises
  at the call site (gut the loop → silent same-family → red); a canned post-mortem citing facts
  absent from the record → grounding red.

### R2 — The verdict schema enforces the spec's taxonomy: process ≠ outcome, hindsight disarmed.
`PostMortem` (pydantic, `extra="forbid"`) carries §6.3's fields EXACTLY — `trade_id`,
`outcome_vs_thesis ∈ {confirmed, refuted, unrelated_path}`, `luck_skill_assessment`,
`premortem_hit: bool`, `lesson{text ≤50 words, generalizable, tags}`, `agent_grades` — plus the two
§6.3 guards as REQUIRED structure: `knowable_at_decision_ts {answer: bool, citations: [refs into
the decision record]}` (hindsight guard — P9's "answered with citations") and **separate**
`process_grade` / `outcome_grade` fields (outcome-bias guard: a profitable trade with a refuted
thesis grades process ≠ outcome — "a loss that paid"), plus `observable_that_would_have_changed`
(the named observable that, seen at decision_ts, would have altered the decision — process-error
vs market-noise is exactly `process_grade` vs `outcome_grade` divergence).
- **Red tests:** missing the knowable answer / merged process-outcome / an out-of-enum
  `outcome_vs_thesis` / a smuggled stance or weight field → ValidationError; a post-mortem whose
  `observable_that_would_have_changed` is empty → rejected as unfinished (the MOD-01 premortem
  pattern).

### R3 — Lessons are CAPTURED append-only, replay-stamped — and NO weight exists anywhere. *(The Phase-3 boundary.)*
Post-mortems and lesson-candidates are captured as **event-log events** (the source of truth,
memory-systems §1) plus a derived episodic store **rebuildable from the log** (a tested rebuild,
not a theory). Every record stamps a ReplayTuple incl. `manifest_version`. The store is
**append-only**: no update/delete API exists; episodes are immutable (§3.1).
**Phase-3 boundary, red-tested:** NO field named/like `weight`, `believability`, `w_i`, `score
multiplier` exists in ANY WP5 schema (episode, lesson, post-mortem) — schemas are `extra="forbid"`
AND an explicit forbidden-name test scans them; the believability store's "no write API" rule
(§5.2) is honored by not building one.
- **Red tests:** a `weights`/`believability` field appearing in any schema → red (the boundary
  test); an attempted episode mutation → red; drop `manifest_version` from the capture stamp → the
  CP0 replay-identity test class goes red; delete-the-derived-store → rebuild-from-log test must
  reproduce it byte-equal.

### R4 — Captured lessons are retrievable — and NOTHING reads them into live decisions in Phase 1.
A retrieval API returns episodes/lessons by ticker / agent / date-range / tags (for future
consumption per §3.2's curated policy). But the Phase-1 live decision path consumes NONE of it:
the §3.2 context injection into P2/P6 is EXPLICITLY deferred (recorded here as the Phase-1 wiring
decision; §3.2's "never during P4/P5" becomes binding when injection wires in later). **Isolation
is structural (the WP3 shadow pattern):** the live-path modules (`graphs/deep_loop.py`, `debate.py`,
`ballot.py`, `pm.py`, `risk_gate.py`, `orders.py`, `monitor.py`, `judge.py`) must not import the
memory store — AST-scan-enforced.
- **Red tests:** an import of the memory module added to any live-path module → scan red;
  retrieval-by-ticker/agent/date tests on constructed records (distinct queries ⇒ distinct
  results — the gut-detector for a hardcoded retriever).

### R5 — Dashboard v1 renders REAL committed records; fake/sample data is structurally impossible.
A $0 static generator (`ops/build_dashboard.py` → HTML) that reads the ACTUAL `results/`
artifacts — the WP3 pipeline (run3 comparison verdict, debate/ballot summaries, PM decisions +
sizing audits, judge scores, shadow decorrelation), the WP4 records (gate allowance audits,
modeled orders/fills, the HALT demo, per-trade costs), the cumulative spend ledger, and current
breaker state. **No sample-data path exists:** a missing artifact FAILS the build (never a
placeholder render).
- **Red tests:** spot-values in the rendered HTML must equal the artifact values (e.g. the 0.7383
  run3 mean, the 0.735% MDT size, margin 0.061, cost 4.2153 bps) — regenerate against a tampered
  copy → mismatch red; delete an artifact → the generator raises (no silent placeholder); a
  source-scan asserts no synthetic/sample-data literals in the generator.

### R6 — Edge rulings, pre-committed.
- **a. Post-mortem on a no_trade — RULED IN SCOPE (Phase-1-lite).** The WP3 COST no_trade gets a
  post-mortem record: counterfactual marks (backfilled, real), `what_would_reopen` reviewed,
  `outcome_vs_thesis` evaluated against the DECLINE rationale. memory-systems §3.1 schedules
  material-no-trade episodes for Phase 2+ — WP5 rules: capture the record NOW (cheap, real);
  the recurring counterfactual-tracking cadence lands with Phase 2 (cited, not skipped silently).
- **b. Open outcome window.** A decision whose horizon hasn't elapsed gets an **INTERIM**
  post-mortem: `interim: true` + `window_days` recorded; interim post-mortems may NOT emit
  `generalizable: true` lesson-candidates (no promotion off partial windows — a lesson from a
  4-day window is an anecdote by construction). Red: an interim record with a generalizable
  lesson → rejected.
- **c. PMORT model unavailable — QUEUED, never skipped.** An LLMError after the client's bounded
  retries emits a `pmort_pending` event (fail-closed); a drain path retries pending post-mortems;
  nothing fabricates a verdict. Red: injected LLMError → pending event present, no post_mortem
  event, and the queue survives restart (read back from the log).

### R7 — The WP5 smoke: one REAL interim post-mortem on the stored MDT decision.
After the SEP backfill lands real marks: one PMORT-01 call (family-disjoint seat) on the stored
MDT decision record + its real partial-window outcome → a schema-valid, grounded, INTERIM-labeled
post-mortem, captured per R3, retrievable per R4, rendered per R5. Committed artifact under
`results/wp5/` with stamps.
- **Red test:** the smoke's post-mortem must reference the REAL entry (80.151027) and real marks —
  a run against an empty outcome window must refuse (R6b/R6c paths), not invent.

## Spend envelope
- **PMORT smoke (R7): ~$0.3–1.0** (one T3 call on a few-KB decision record + retry headroom;
  possibly one more for the R6a no-trade case — cap the WP5 smoke at **$2**).
- **$0:** SEP backfill (subscription data, existing ingestion path), capture/retrieval plumbing,
  isolation scans, dashboard generator, all red tests.

## Build order (after Akshar's gate)
1. SEP backfill for MDT/COST outcome window ($0, data-layer; hash-locked fixture-style evidence).
2. Schemas + event-log capture + derived store + rebuild test (R2, R3).
3. Retrieval + isolation scans (R4).
4. PMORT-01 runner reusing the judge plumbing (R1, R6b/c paths).
5. Dashboard v1 (R5).
6. Red tests + gut demos (standing practice), full suite, vendor scan.
7. Smoke (R7 + R6a) [paid, ≤$2] → readout → PR.

## Standing rules (unchanged)
Committed re-runnable tests; gut-demos red-then-restored; fixtures/licensed data never committed
(backfill marks live in the pit_store; only derived/locked evidence commits); vendor scan every
commit; ReplayTuples with `manifest_version` everywhere; branch + PR; **no self-merge**.

**Gate (Akshar).** Approve R1–R7 + the data-reality framing (interim-only post-mortems until WP6)
+ the ≤$2 smoke cap, BEFORE any implementation code. Zero spend this checkpoint.
