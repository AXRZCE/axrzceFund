# WP1 — LangGraph deep-loop skeleton on stubs: done-criteria + rulings

**Committed BEFORE implementation code** (brief §1.1). Binding specs:
`architecture.md` (deep-loop topology + §7.3 replay tuple), `decision-protocols.md`
(P1–P7, P10, P12), `agent-specifications.md` §2 (schemas) + §7 (roster).
**Goal:** prove the state machine — checkpointing, kill/resume, fail-closed — with
**ZERO LLM spend**. Only the agents are stubs; the skeleton's own behavior is real.

## Rulings (decided a priori)

- **R1 — Graph state = the decision-record contract, field-for-field.** The memo
  models (`ResearchMemo`, `DebateTurn`, `TradeProposal`) mirror `agent-specifications.md`
  §2 exactly. `CycleState` aggregates them plus *loop-orchestration* fields
  (candidate, halted/halt_reason, failure, per-stage outputs) — orchestration
  bookkeeping, not invented memo content. If a §2 schema looks wrong, flag it
  (which-of-code/test/spec), do not patch it.
- **R2 — Determinism definition.** A stub cycle's decision *content* is deterministic;
  only the replay-identity fields vary per run. Ruling: **the replay compare excludes
  the replay-identity fields `{cycle_id, decision_ts, trade_id}`** (definitionally
  per-run; `cycle_id`/`decision_ts` are top-level, `trade_id` is nested in the
  `decision` payload). "Replay" = re-invoke the graph with the **same initial state**
  (same cycle_id/decision_ts) on a fresh checkpointer/event-log; every other field of
  the final `CycleState` must be byte-identical. (Chosen over injecting a fake
  clock/ID, which would falsify the replay tuple itself.) *Refinement (post-commit):
  trade_id added to the excluded set — it was missed in the first cut; the principle
  (exclude per-run identity) is unchanged.*
- **R3 — Checkpointing.** Checkpoint **after every node** so a mid-cycle kill resumes
  exactly. Checkpointer DB = `var/checkpoints.sqlite`, **separate** from the event
  log (`core/event_log.py` remains the immutable source of truth). A run **killed**
  (SIGKILL) resumes from its last checkpoint to the same final state; a run that
  **fails** (a node raises) **halts and is NOT auto-resumed** — different behaviors.
- **R4 — Fail-closed = precise safe state.** On a node exception: emit **no**
  intended-order/decision event; write a `cycle_failed` event to `core/event_log.py`
  carrying `cycle_id` + failing node id; halt the cycle (no downstream nodes run);
  leave a **terminal, non-resumable** checkpoint.
- **R5 — No broker / no OrderManager in WP1 (that is WP4).** The terminal node emits
  an **intended-order / decision event** to the event log ONLY — it does not call a
  broker and does not stub a fake submission. "Zero orders emitted" in the
  fail-closed test = that event is absent.
- **R6 — Full Phase-1 roster wired as stubs** so WP2–WP5 swap stubs for real agents
  without re-wiring: FUND-TECH, TECH-01, SENT-01, BULL-01, BEAR-01, MOD-01, PM-01,
  PMORT-01, VERIF-01. Stubs are the ONLY canned code in Phase 1: each `Stub<Role>`,
  in `graphs/stubs/` only, docstring "replaced in WP2", returning clearly-fake memos.

## Node order (decision-protocols.md)
P1 cycle_open → P2 research (FUND-TECH, TECH-01, SENT-01) → VERIF-01 strip →
P3 debate_gate → P4 debate (BULL, BEAR, MOD) → P5 sealed ballot → P6 PM proposal →
P7 code risk-gate → terminal (emit decision event) → P9/P10 (PMORT-01 + cycle seal).

## Done (each demonstrable, not asserted)
1. End-to-end stub cycle runs; `core/replay.py` reproduces it (per R2 compare).
2. **Kill-and-resume:** a test that actually SIGKILLs the cycle mid-run, restarts,
   and gets the identical final state from the checkpoint.
3. **Fail-closed:** a test that injects a node exception → graph halts, intended-order
   event absent, `cycle_failed` event logged with cycle + node.
4. **Zero LLM spend, two ways:** (a) `tests/test_no_llm_in_skeleton.py` greps
   `graphs/` and asserts no LLM SDK import (`anthropic`, `openai`) — same shape as the
   vendor-leakage gate; (b) the LLM client is monkeypatched to raise if called, and a
   full cycle confirms it never fires.
5. **Stubs confined:** no `Stub*` imported outside `graphs/stubs/` + `graphs/deep_loop.py`.
6. Every event carries a `ReplayTuple`; hash-chain integrity intact.

Standing rule (from WP0): every load-bearing proof is a committed, re-runnable test;
no deleted one-offs. WP1 has no broker dependency (that gates WP4).
