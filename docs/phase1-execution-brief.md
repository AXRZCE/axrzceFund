# Phase 1 Execution Brief — axrzceFund

**Audience:** Claude Code, running on the always-on VM under the project venv, isolated from ANTS.
**Status:** G0 memo signed (2026-06-24). Phase 1 is open.
**Authority:** This brief governs *how* you build and *what "done" means*. It does **not**
re-specify component internals — the binding specs live in `docs/`. Where this brief and a
`docs/` spec disagree on a component's behavior, **the spec wins; stop and flag the conflict**
rather than guessing.

---

## 0. Prime directive — the anti-hoax contract

Phase 1 is the smallest *honest* fund. "Honest" is the whole point of the project, so the
single rule that overrides convenience is:

> **Nothing is "done" unless it is demonstrable on real or recorded-real data, covered by a
> test that would FAIL if the implementation were gutted, and recorded in the audit trail.**

Concretely, the following are **forbidden in any code you mark complete**:

- `raise NotImplementedError`, a bare `pass` as a function body, or `...` as a body.
- `# TODO`, `# FIXME`, `# placeholder`, `# stub`, `# mock for now` left in shipped code.
- A function that returns a **hardcoded literal** where real computation is claimed.
- A test that asserts `True`, asserts the function "ran", or mocks the very thing under test
  so thoroughly that gutting the implementation still passes.
- A dashboard, report, or metric wired to **demo/seed numbers** instead of the real store.
  (This is the canonical hoax and is explicitly banned.)

**The one legitimate exception** is the WP1 skeleton stubs. They are *deliberately* canned,
and they are quarantined: every stub agent is named `Stub<Role>`, lives only in
`graphs/stubs/`, and carries a module docstring saying it is replaced in WP2. A canned return
anywhere outside `graphs/stubs/` is a hoax, not a stub.

**Self-check for every PR:** "If a skeptical outsider replaced this function body with
`return <fake>`, would any test go red?" If no — the test is theatre. Fix the test before
merging.

---

## 1. Discipline carried from Phase 0 (do not relax)

These are why G0 meant something. They apply unchanged.

1. **Commit the criteria before the evidence.** At the start of each work package (WP),
   before writing implementation code, commit (a) the WP's definition-of-done and (b) any
   edge-case rulings you can foresee, to git. No post-hoc redefinition of "pass."
2. **On any failure, ask: which of code / test / spec is wrong?** Diagnose, then fix the
   wrong one. Never force a green by loosening a threshold to match a result.
3. **No look-ahead, ever.** Every data read goes through `data/pit_store.py` with an explicit
   `as_known_at`. No agent or node touches a vendor SDK or a raw file directly.
4. **Audit trail is a deliverable.** Every WP ends with a short readout committed to `docs/`
   (mirroring `g01-readout-*.json`, `g04-replay-*.json`) and the relevant events written to
   `core/event_log.py`. The event log is the source of truth; everything else is a derived view.
5. **Isolation.** Own venv, own `.env`, project root only. Never read, write, or import
   anything from the co-resident ANTS project.
6. **Branch + PR per WP.** `phase1/wp<N>-<slug>`. Small, reviewable commits. The human reads
   the PR; you do not self-merge a gate.

---

## 2. Source-of-truth map — read before you build, do not paraphrase

For each component, the listed doc is binding. Read the cited section *at the start of the WP*,
implement to it exactly, and if the spec looks wrong, **flag it (which-of-code/test/spec)
instead of "improving" it.**

| Component | Binding spec |
|---|---|
| Deep-loop topology, ADRs, replay tuple | `docs/architecture.md` |
| Agent roster + per-agent memo schemas | `docs/agent-specifications.md` (§7) |
| Protocols P1–P12 (research, debate, ballot, PM, risk gate, learning) | `docs/decision-protocols.md` |
| Vendor interface contracts (R5) | `docs/api-data-sources.md` (R5) |
| CPCV / DSR / PSR / PBO / golden-day fixtures / ensemble comparison | `docs/backtesting-framework.md` (§7 for ensemble) |
| Episodic memory, probation queue, believability version tuple | `docs/memory-systems.md` (§8) |
| Breaker conditions, fail-closed behavior, failure taxonomy | `docs/failure-modes-mitigation.md` |
| Limits, thresholds, config hashing | `docs/configuration.md` |
| Dashboard metrics, MinTRL countdown | `docs/monitoring-metrics.md` |
| Exit-gate numbers (G1.1–G1.4), schema-conformance bar, MinTRL math | `docs/validation-criteria.md` |

---

## 3. Integration invariants — build ON the existing spine, never reinvent it

The G0 modules already exist and are the substrate. Phase 1 plugs into them:

- **Every decision/artifact carries a `ReplayTuple`** (`core/replay.py`):
  `(trade_id, cycle_id, decision_ts, agent_id, prompt_version, model_version, config_version,
  code_version)`. No agent output is recorded without one.
- **Every meaningful step emits an `Event`** to `core/event_log.py` (`memo_written`,
  `ballot_cast`, `order_submitted`, etc.). Hash-chain integrity must remain intact.
- **Every data read goes through `data/pit_store.py`** (`var/pit_store.duckdb`) with
  `as_known_at = decision_ts`. Layer-1 read filter guarantees no future rows. If you find
  yourself wanting a vendor call inside an agent, that is the R5 violation WP0 exists to prevent.
- **Every backtest/eval registers in `harness/trial_registry.py` first** — the API refuses an
  unregistered `trial_id`. Phase 1's first signal-admission run (parallel track) obeys this.
- **CPCV + DSR/PSR/PBO** statistics come from `harness/` — do not write a second statistics path.

---

## 4. Phase 1 scope (from `implementation-plan.md` — do not exceed)

**IN:** FUND-TECH, TECH-01, SENT-01, BULL-01, BEAR-01, MOD-01, PM-01, PMORT-01 + VERIF-01
service; protocols P1–P7 (**gate-only risk — no RISKA agent**), P9, P10, P12; episodic memory +
probation queue + believability **recording** (not weighting); long-only or long + ETF hedge;
simple execution (market-on-open / limit, **no EXEC-01**); breakers active (whole book = one pod).

**OUT (deliberately — do not build):** believability *weighting* (record only), intraday
escalation mini-graph (monitors + stops only), QUANT-01 (no admitted signals yet), MACRO-01,
multi-sector, shorts beyond hedges, META-01.

If a WP tempts you to build something on the OUT list, stop — that is Phase 2.

---

## 5. Work packages

Each WP: **read-first → build → definition-of-done (demonstrable) → commit → anti-hoax check.**
Commit the done-criteria to git *before* writing code (§1.1). Do WPs in order; WP0 is a hard
prerequisite for everything else.

### WP0 — Repay R5 (vendor interface adapters) + housekeeping
The one genuine architecture deviation from Phase 0. Close it before any agent reads data.

- **Read first:** `api-data-sources.md` (R5 + the four interface contracts), `architecture.md`
  (boundary rules).
- **Build:**
  - `data/interfaces/` — four ABCs with method signatures exactly per R5:
    `MarketDataInterface`, `FundamentalsInterface`, `BrokerInterface`, `DocumentsInterface`.
  - Concrete adapters for the three Phase 1 needs: `AlpacaMarketData`, `SharadarFundamentals`,
    `AlpacaBroker`. `DocumentsInterface` ABC is defined but has no concrete impl yet (no Phase 1
    agent reads filings) — leave the interface, do **not** leave dead code or a `NotImplementedError`
    body; simply don't instantiate it.
  - Refactor `data/ingestion.py`, `ops/broker_roundtrip.py`, `ops/verify_alpaca.py`,
    `ops/verify_sharadar.py` to call **only** through adapters. Vendor SDK imports
    (`alpaca`, `nasdaqdatalink`) must exist **only** inside the adapter modules.
  - Delete the dead Windows-era files: `ops/g05_run.cmd`, `ops/nightly_ingest.cmd`,
    `ops/wake_test.cmd`.
- **Done (demonstrable):**
  - `tests/test_no_vendor_leakage.py` greps the tree and asserts vendor imports appear **only**
    under `data/interfaces/`. Green.
  - The G0 ops still pass *through the adapters*: nightly ingest archive byte-identical to a
    prior night (replay determinism preserved); broker round-trip = 10 orders, 0 mismatches;
    `ops/replay_check.py` passes.
  - All existing tests green.
- **Anti-hoax check:** at least one **real** integration run hits the live Sharadar/Alpaca
  (paper/historical) *through the adapter* and returns real rows — proving the adapter wraps the
  SDK, not a mock.

### WP1 — LangGraph deep-loop skeleton on stub agents
Prove the state machine with **zero LLM spend**.

- **Read first:** `architecture.md` (deep-loop topology), `decision-protocols.md` (P1, P10, P12 —
  loop-level protocols), `agent-specifications.md` §7 (roster + cycle shape).
- **Build:**
  - `graphs/deep_loop.py` — the LangGraph `StateGraph`: a typed (pydantic) graph state capturing
    the full decision record; one node per roster slot (stubbed); edges in protocol order.
  - `graphs/stubs/` — `StubTECH01`, `StubBULL01`, … returning clearly-fake canned memos.
    (The only legitimate canned code in Phase 1 — quarantined and named `Stub*`.)
  - **Checkpointing** wired to durable storage (LangGraph checkpointer, e.g. SQLite). A cycle
    killed mid-run resumes from the last checkpoint to the *same* end state.
  - **Fail-closed**: a node that raises halts the graph in a safe state that emits **no order**
    and logs the failure to `core/event_log.py`. Add a fault-injection switch for the test.
- **Done (demonstrable):**
  - End-to-end cycle runs deterministically on stubs; replay via `core/replay.py` reproduces it.
  - **Kill-and-resume test:** SIGKILL mid-cycle → restart → identical final state.
  - **Fail-closed test:** injected node exception → graph halts, zero orders, failure event logged.
  - **Zero LLM calls:** the Anthropic client is monkeypatched to raise if called; test confirms
    it never fires.
- **Anti-hoax check:** the skeleton's own behavior (transitions, checkpoint, fail-closed) is real
  and tested; only the agents are stubs, and they cannot escape `graphs/stubs/`.

### WP2 — Real agents, one at a time, vs post-cutoff golden-day fixtures
Replace stubs with real LLM agents, each proven on recorded historical days that **postdate the
model's training cutoff** (no look-ahead, no memorization).

- **Read first:** `agent-specifications.md` §7 (each agent's contract + memo schema),
  `decision-protocols.md` (P2 independent research + the VERIF-01 strip protocol),
  `backtesting-framework.md` (golden-day fixture method), `validation-criteria.md` (schema bar).
- **Build:**
  - `data/fixtures/` harness: record real historical trading days (prices via SEP, fundamentals
    via SFA as-of, the sentiment source for SENT-01) into replayable fixtures.
    **Hard precondition (day-one non-negotiable):** the loader verifies each fixture's date is
    **> model training cutoff** before the fixture can be used; a fixture failing this is rejected.
    A test enforces the rejection.
  - **VERIF-01** service: validates/strips agent memos per spec.
  - Implement agents **one at a time**, data-only first then interpretive: TECH-01 → FUND-TECH →
    SENT-01 (and any other in-scope P2 research agent). Each makes a real LLM call, returns a
    schema-conformant memo, reads **only** via `pit_store`, and is budget-metered per call.
- **Done (per agent, demonstrable):**
  - Produces a schema-valid memo on the fixture (validated against the spec schema; test fails on
    drift).
  - VERIF-01 strips/flags a *constructed* bad memo correctly.
  - Budget metering records real token cost.
  - Replay tuple captures `prompt_version` + `model_version`; the decision record is reconstructable.
  - Look-ahead audit clean: every read traced to `pit_store` with `as_of`/`available_at`.
- **Anti-hoax check:** replacing an agent body with a canned memo must turn its test red. Each
  agent's memo is grounded in *that fixture's* data, verifiably.

### WP3 — Debate + ballot + PM, and shadow-ensemble from the first debate
The adversarial core, plus the standing day-one experiment.

- **Read first:** `decision-protocols.md` (P3–P7 debate/ballot/PM), `agent-specifications.md` §7
  (BULL/BEAR/MOD/PM contracts), `backtesting-framework.md` §7 (ensemble comparison).
- **Build:**
  - BULL-01, BEAR-01, MOD-01, PM-01 nodes wired into the deep loop (replacing those stubs).
  - Ballot mechanism + PM decision record exactly per protocol.
  - **Conformity-event logging live from the first debate.**
  - **Shadow-ensemble (day-one non-negotiable):** every cycle *also* computes the
    independent-ensemble decision — votes straight from the P2 memos, **no debate** — logged, not
    traded. The debate-vs-ensemble delta is queryable from the event log.
- **Done (demonstrable):**
  - A full debate on a fixture yields per-agent arguments + a ballot + a PM decision record, all
    schema-valid and logged.
  - A *constructed* conformity case triggers a real conformity event (not a counter stuck at zero).
  - The shadow-ensemble decision is computed and logged beside every debated decision.
- **Anti-hoax check:** on at least one fixture, BULL and BEAR reach *different* conclusions from
  the same data, and the shadow decision can differ from the debate decision. Universal agreement,
  or shadow ≡ debate every time, is a signal to investigate — not to ship.

### WP4 — Risk gate + order manager + intraday monitor
Gate-only risk (no RISKA). The deferred OrderManager lands here.

- **Read first:** `decision-protocols.md` (the in-scope gate protocols — gate-only),
  `failure-modes-mitigation.md` (breaker conditions), `architecture.md` (order path),
  `configuration.md` (limits/thresholds).
- **Build:**
  - **Risk gate:** deterministic, emotion-free checks per spec; vetoes a PM decision that breaches
    a configured limit.
  - **OrderManager:** routes orders through `BrokerInterface` (WP0) in paper mode; market-on-open /
    limit only (no EXEC-01). Tracks fills, computes fill divergence vs modeled.
  - **Intraday monitor loop:** stops, invalidation conditions, breakers (whole book = one pod).
- **Done (demonstrable):**
  - Risk gate **vetoes a constructed breach** and **passes a clean decision** — test proves both.
  - Orders flow OrderManager → BrokerInterface → Alpaca **paper**; a placed paper order is
    confirmed and reconciled (agent-driven round-trip, like G0.5).
  - A simulated breaker condition trips and halts new orders; the trip is logged.
  - Fill divergence computed on a real paper fill.
- **Anti-hoax check:** the gate must actually reject a real constructed breach (not log
  "checked: ok" unconditionally); orders must reach the real Alpaca paper endpoint and return
  confirmed — proven by reconciliation, not a mock that always says "filled."

### WP5 — Learning loop (P9) + post-mortem (PMORT-01) + consolidation + dashboard v1
Close the loop. The deferred MinTRL calculator lands here.

- **Read first:** `memory-systems.md` §8 (episodic memory, probation queue, believability version
  tuple), `decision-protocols.md` (P9), `agent-specifications.md` §7 (PMORT-01),
  `monitoring-metrics.md` (dashboard), `validation-criteria.md` (MinTRL math).
- **Build:**
  - Episodic memory write on every closed trade (real inputs/decision/outcome).
  - **PMORT-01** post-mortem agent: runs after a closed trade, produces a structured post-mortem
    feeding the lesson pipeline.
  - **Probation queue + lesson promotion:** a candidate lesson traverses the *full* probation
    pipeline before it can influence anything. Believability is **recorded only** (not weighting —
    scope OUT), keyed by the correct version tuple.
  - Consolidation job (periodic memory consolidation per §8).
  - **MinTRL calculator** → countdown widget.
  - **Dashboard v1:** P&L, exposures, costs, MinTRL countdown, fill divergence — all from the real
    event log / store.
- **Done (demonstrable):**
  - A closed trade writes a queryable episode.
  - PMORT-01 produces a real post-mortem on a closed trade.
  - **One lesson is promoted through the full probation pipeline end-to-end** (G1.4) — and a
    *failing* candidate is demonstrably **not** promoted.
  - Believability records populate with the right version tuple.
  - Dashboard renders **real** numbers from the store.
- **Anti-hoax check:** the dashboard reads the real store (demo numbers forbidden); the probation
  pipeline actually gates (prove with both a passing and a failing candidate).

### WP6 — Dry-run week (operational proof, no new build)
- **Read first:** `implementation-plan.md` §Phase 1 step 6; `validation-criteria.md` (what a clean
  decision record must contain).
- **Activity:** run the full daily loop each trading day for a week. Orders **generated and logged
  but NOT submitted.** The human reviews **every** decision record for protocol fidelity, schema,
  look-ahead audit, conformity events, and the shadow-ensemble delta.
- **Pre-commit ruling (before the week starts):** any defect → which-of-code/test/spec → fix →
  the dry-run clock **restarts** (same standard as the soak). Commit this rule first.
- **Done:** a clean dry-run week with every decision record passing human review.
- **Anti-hoax check:** this is the human gate on the whole pipeline; it exists to catch a decision
  record that *looks* right but isn't grounded. Do not shortcut it.

### WP7 — Go live on paper + open the G1 clock
- **Activity:** flip to live paper submission via the OrderManager. Begin E1 accumulation.
- **Note:** going live is **not** the end of Phase 1. The exit gate is the ≥3-month E1 record,
  which is *accumulation, not construction.* No Phase 2 build until G1 is met and signed — the
  same human-gate discipline as G0. Be patient; that patience is what makes the record mean
  something.

---

## 6. Phase 1 exit gate (G1) — commit these now, before the evidence

Exact numbers live in `validation-criteria.md`; the shape:

- **G1.1 Operational:** ≥60 consecutive trading days, zero unexplained halts, look-ahead audit
  clean, reconciliation clean.
- **G1.2 Protocol quality:** memo strip rate, role-violation rate, conformity-event rate all below
  thresholds; cost per decision within budget.
- **G1.3 Evidence:** ≥3 months E1, ≥40 closed trades; performance vs *both* benchmarks with PSR
  reported. **The gate here is "the machine works and the record is interpretable," not "alpha is
  proven"** — MinTRL math says 3 months cannot prove alpha, and pretending otherwise would violate
  our own framework.
- **G1.4 Learning loop:** ≥1 lesson promoted through the full probation pipeline; believability
  records populating correctly per version tuple.

When G1 is met, write the G1 memo (same form as the G0 memo: each criterion against its artifact,
plus the honest history) and hand it to the human. **Do not self-certify.**

---

## 7. Per-commit anti-hoax checklist (the human will audit against this)

Before every PR merge, all must hold:

- [ ] No `NotImplementedError` / bare `pass` body / `...` body in shipped code.
- [ ] No `# TODO` / `# FIXME` / `# placeholder` in code marked done.
- [ ] No hardcoded-literal return where computation is claimed (except quarantined `graphs/stubs/`).
- [ ] Every new module has tests that exercise the **real** path on real/fixture data.
- [ ] Each test would **go red** if the implementation were replaced by a fake return.
- [ ] At least one integration run per data/broker WP hits the **real** API (paper/historical).
- [ ] Every decision/artifact carries a `ReplayTuple`; every step emits the right `Event`.
- [ ] Every data read is via `pit_store` with explicit `as_known_at`; look-ahead audit clean.
- [ ] No import from ANTS; vendor SDKs only inside `data/interfaces/`.
- [ ] A WP readout is committed to `docs/`; done-criteria were committed *before* the code.

---

## 8. How to drive this

This is a multi-session build (the plan estimates 4–6 weeks, then ≥3 months of accumulation).
Run it **one WP per focused session**, in order. At the start of each session: re-read this brief's
WP section, read the governing `docs/` spec, commit the WP done-criteria, then build. End each
session with the readout and a PR for human review. WP0 first — no agent work begins until R5 is
repaid and `test_no_vendor_leakage.py` is green.
