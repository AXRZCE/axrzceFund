# WP1 readout — LangGraph deep-loop skeleton on stubs

**Branch:** `phase1/wp1-skeleton`. **Done-criteria (before code):** `05cf3b5`,
rulings R1–R7. **Goal met:** the state machine is proven — durable checkpointing,
real kill/resume, fail-closed — with **zero LLM spend**.

## What changed
- `graphs/state.py` — `CycleState` decision record = agent-specifications §2
  field-for-field (`ResearchMemo`/`DebateTurn`/`TradeProposal`/`Ballot`), plus the
  replay compare (`replay_comparable()`).
- `graphs/stubs/` — nine quarantined `Stub<Role>` agents (replaced in WP2).
- `graphs/deep_loop.py` — LangGraph `StateGraph` in protocol order (P1→P7→terminal),
  durable `SqliteSaver` checkpointer (`var/checkpoints.sqlite`), fail-closed routing,
  `FaultInjector` + native `interrupt_before` test hooks. Terminal emits an
  intended-order/decision EVENT only — no broker.
- Tests: `test_deep_loop.py`, `test_no_llm_in_skeleton.py`,
  `tests/integration/test_kill_resume.py` (+ runner).

## Evidence (each demonstrable, not asserted)
| Criterion | Result |
|---|---|
| Clean cycle runs end-to-end | ✅ emits `intended_order`, 10 nodes, clean hash chain |
| **Replay reproduces** (R2) | ✅ same-cycle replay byte-identical under `replay_comparable()`; excludes only labels `{cycle_id, trade_id}`, **keeps `decision_ts`** (the PIT boundary — a replay that read different data must fail) |
| **Kill-and-resume** (R7, Linux/VM) | ✅ **real SIGKILL** of a subprocess mid-cycle (after `ballot` checkpointed, before `pm`); resume from the on-disk checkpoint **continued** — pre-kill events **exactly once** (`ballot_cast`==3, not 6 → no restart/duplicate) and final == clean run. `tests/integration/test_kill_resume.py`, passed on the VM (Python 3.12, Linux). |
| **Fail-closed** (R4/R5) | ✅ injected node exception → halt, `cycle_failed` logged (cycle+node), NO decision event, downstream nodes skipped (incl. a failure at `terminal` itself) |
| **Zero LLM, two ways** | ✅ grep `graphs/` for `anthropic`/`openai` (none) + a monkeypatch booby-trap that raises on ANY LLM attribute access while a full cycle still completes |
| Stubs confined | ✅ `graphs.stubs` imported only in `graphs/stubs/` + `graphs/deep_loop.py` |
| ReplayTuple on every event | ✅ `decision_ts` = cycle boundary (constructed directly, not `now()`) |

Default suite **121 passed** (4 integration deselected); integration (`pytest -m
integration`): equivalence ×3 + kill-resume — all pass with creds/Linux.

## Notes
- Two ruling refinements during the build, both committed: `trade_id` added to the
  replay-identity exclusion (nested in `decision`); `decision_ts` **removed** from
  the exclusion (it is causal, not a label — reviewer catch).
- Dependency added: `langgraph-checkpoint-sqlite` (durable checkpointer).
- No broker / OrderManager (WP4). No real agents (WP2).
