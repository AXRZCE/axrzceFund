"""LangGraph deep-loop skeleton (WP1) — proves the state machine on stub agents with
ZERO LLM spend. Nodes run in protocol order (decision-protocols.md P1→P7→terminal);
the graph itself (transitions, durable checkpointing, fail-closed routing) is REAL
and tested — only the agents are stubs.

Rulings (docs/wp1-skeleton-done-criteria.md): checkpoint after every node into
var/checkpoints.sqlite (R3, separate from the event log); a node exception →
fail-closed (R4): emit no decision event, log a `cycle_failed` event with cycle+node,
route straight to END (no downstream node runs). The terminal node emits an
intended-order/decision EVENT only — no broker, no order (R5; broker is WP4).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from core.event_log import EventLog
from core.replay import ReplayTuple, new_trade_id
from graphs.ballot import tally
from graphs.state import CycleState
from graphs.stubs import (
    StubFUNDTECH,
    StubPM01,
    StubPMORT01,
    StubSENT01,
    StubTECH01,
    StubVERIF01,
    StubVoters,
)

# configuration.md §4 (P5): margin below this fraction of total cast weight = CONTESTED.
# Read once at import from the config file — a missing param is a build error by policy (§11).
from core.config import param_number

BALLOT_MARGIN_THRESHOLD = param_number("ballot_margin_threshold")

# WP3 CP2 (R2): the debate node takes an INJECTED implementation — the WP1 debate stubs were
# removed when the real machinery (graphs/debate.py) landed. deep_loop deliberately does NOT
# import graphs.debate (which needs the LLM client): production wiring injects it; tests inject
# doubles. An un-wired debate node fails closed.
DebateImpl = Callable[[CycleState], dict]

CHECKPOINT_PATH = Path("var/checkpoints.sqlite")
# Linear protocol order; the fail-closed router sends any node to END on halt.
NODE_ORDER = [
    "cycle_open", "research", "verify", "debate_gate", "debate",
    "ballot", "pm", "risk_gate", "terminal", "post_mortem",
]


class FaultInjector:
    """Test hook: makes a named node raise a chosen exception, to exercise fail-closed (R4).

    `exc` lets a test assert a SPECIFIC failure (e.g. an agent's LLMError) is caught the same
    fail-closed way as any node exception."""

    def __init__(self, fail_at_node: Optional[str] = None, exc: type[Exception] = RuntimeError):
        self.fail_at_node = fail_at_node
        self.exc = exc

    def check(self, node: str) -> None:
        if node == self.fail_at_node:
            raise self.exc(f"injected fault at node '{node}'")


def _replay_payload(state: CycleState, agent_id: str, extra: dict) -> dict:
    # decision_ts = the cycle's information boundary (architecture §7.3), not stamp time.
    rt = ReplayTuple(
        trade_id=(state.decision or {}).get("trade_id") or new_trade_id(),
        cycle_id=state.cycle_id, decision_ts=state.decision_ts, agent_id=agent_id,
        prompt_version="stub", model_version="stub", manifest_version="stub",  # stub loop loads no manifest
        config_version=state.config_version, code_version=state.code_version,
    )
    return {"replay_tuple": rt.to_dict(), **extra}


def build_deep_loop(event_log: EventLog, fault: Optional[FaultInjector] = None,
                    checkpoint_path: Path = CHECKPOINT_PATH,
                    interrupt_before: Optional[list[str]] = None,
                    *, debate_impl: Optional[DebateImpl] = None):
    """Compile the deep-loop graph with a durable SQLite checkpointer.

    `interrupt_before` (LangGraph native) pauses execution before the named nodes —
    used by the kill-resume test to stop after a checkpoint exists but before a mid
    node runs, so the subprocess can be SIGKILLed at a known boundary.

    `debate_impl` (WP3 CP2): the debate node's implementation — production injects the real
    graphs.debate machinery (make_debate_node in the production wiring); tests inject doubles.
    None ⇒ the debate node FAILS CLOSED (halt), never a canned debate.
    """
    fault = fault or FaultInjector()
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    def safe(name: str, fn: Callable[[CycleState], dict]) -> Callable[[CycleState], dict]:
        """Wrap a node: no-op if already halted; on exception, fail-closed (R4)."""
        def node(state: CycleState) -> dict:
            if state.halted:
                return {}
            try:
                fault.check(name)
                updates = fn(state)
                return {**updates, "completed_nodes": state.completed_nodes + [name]}
            except Exception as e:  # fail-closed
                event_log.append(
                    event_type="cycle_failed", cycle_id=state.cycle_id, agent_id=name,
                    payload=_replay_payload(state, name, {"node": name, "error": str(e)}))
                return {"halted": True, "failure": {"node": name, "error": str(e)}}
        return node

    # ── node bodies (each wraps a stub; pure w.r.t. state) ───────────────────
    def cycle_open(state: CycleState) -> dict:
        candidate = state.candidate or "AAPL"  # P1 stub screening
        event_log.append(event_type="cycle_open", cycle_id=state.cycle_id,
                         payload=_replay_payload(state, "P1", {"candidate": candidate}))
        return {"candidate": candidate}

    def research(state: CycleState) -> dict:  # P2 independent memos
        memos = [s.run(state.candidate) for s in (StubFUNDTECH(), StubTECH01(), StubSENT01())]
        for m in memos:
            event_log.append(event_type="memo_written", cycle_id=state.cycle_id, agent_id=m.agent_id,
                             payload=_replay_payload(state, m.agent_id, {"ticker": m.ticker}))
        return {"research_memos": memos}

    def verify(state: CycleState) -> dict:  # VERIF-01
        kept, flags = StubVERIF01().run(state.research_memos)
        return {"verified_memos": kept, "verifier_flags": flags}

    def debate_gate(state: CycleState) -> dict:  # P3
        return {"debate_eligible": True}

    def debate(state: CycleState) -> dict:  # P4 — injected implementation (WP3 CP2, R2)
        if debate_impl is None:
            raise RuntimeError(
                "no debate implementation wired: the WP1 debate stubs were removed in WP3 CP2 "
                "(R2). Inject debate_impl (production: graphs.debate; tests: a double). Fail-closed."
            )
        updates = debate_impl(state)
        for t in updates.get("debate_turns", []):
            event_log.append(event_type="debate_turn", cycle_id=state.cycle_id, agent_id=t.agent_id,
                             payload=_replay_payload(state, t.agent_id, {"position": t.position}))
        return updates

    def ballot(state: CycleState) -> dict:  # P5 sealed — REAL tally (WP3 CP2, R3)
        votes = StubVoters().cast()  # skeleton votes (real casting = graphs/debate.cast_votes)
        for v in votes:
            event_log.append(event_type="ballot_cast", cycle_id=state.cycle_id, agent_id=v.voter,
                             payload=_replay_payload(state, v.voter, {"sealed": True}))
        # the P5 tally is computed from the sealed votes — the WP1 hardcode is gone (R3)
        summary, _direction = tally(votes, margin_threshold=BALLOT_MARGIN_THRESHOLD)
        return {"ballot": votes, "ballot_summary": summary}

    def pm(state: CycleState) -> dict:  # P6
        proposal = StubPM01().propose(state.candidate, state.ballot_summary, state.premortem_top_risks)
        event_log.append(event_type="proposal_written", cycle_id=state.cycle_id, agent_id="PM-01",
                         payload=_replay_payload(state, "PM-01", {"direction": proposal.direction}))
        return {"proposal": proposal}

    def risk_gate(state: CycleState) -> dict:  # P7 code gate (deterministic, gate-only)
        p = state.proposal
        ok = p is not None and 0 < p.size_pct_nav <= 5.0  # stub limit
        return {"risk_gate_passed": ok, "risk_gate_reason": "ok" if ok else "size breach"}

    def terminal(state: CycleState) -> dict:  # emit intended-order/decision EVENT (no broker, R5)
        if not state.risk_gate_passed:
            event_log.append(event_type="no_trade", cycle_id=state.cycle_id,
                             payload=_replay_payload(state, "PM-01", {"reason": state.risk_gate_reason}))
            return {"decision": {"cycle_id": state.cycle_id, "action": "no_trade"}}
        decision = {"cycle_id": state.cycle_id, "trade_id": new_trade_id(),
                    "ticker": state.candidate, "direction": state.proposal.direction,
                    "size_pct_nav": state.proposal.size_pct_nav, "action": "intended_order"}
        event_log.append(event_type="intended_order", cycle_id=state.cycle_id, agent_id="PM-01",
                         payload=_replay_payload(state, "PM-01", decision))
        return {"decision": decision}

    def post_mortem(state: CycleState) -> dict:  # P9 hook (post-close in WP5)
        return {"post_mortem": StubPMORT01().run(state.decision or {"cycle_id": state.cycle_id})}

    bodies = {
        "cycle_open": cycle_open, "research": research, "verify": verify,
        "debate_gate": debate_gate, "debate": debate, "ballot": ballot, "pm": pm,
        "risk_gate": risk_gate, "terminal": terminal, "post_mortem": post_mortem,
    }

    graph = StateGraph(CycleState)
    for name in NODE_ORDER:
        graph.add_node(name, safe(name, bodies[name]))
    graph.add_edge(START, NODE_ORDER[0])
    for i, name in enumerate(NODE_ORDER):
        if i + 1 < len(NODE_ORDER):
            nxt = NODE_ORDER[i + 1]
            graph.add_conditional_edges(name, (lambda nxt: lambda s: END if s.halted else nxt)(nxt))
        else:
            graph.add_edge(name, END)

    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    return graph.compile(checkpointer=saver, interrupt_before=interrupt_before or [])


def new_cycle_state(config_version: str = "stub_cfg", code_version: str = "wp1") -> CycleState:
    from core.replay import new_cycle_id
    now = datetime.now(timezone.utc)
    return CycleState(
        cycle_id=new_cycle_id(1, now.strftime("%Y%m%d")),
        decision_ts=now.isoformat(), config_version=config_version, code_version=code_version)


def run_cycle(event_log: EventLog, fault: Optional[FaultInjector] = None,
              checkpoint_path: Path = CHECKPOINT_PATH,
              initial: Optional[CycleState] = None,
              *, debate_impl: Optional[DebateImpl] = None) -> CycleState:
    """Run one deep-loop cycle; returns the final CycleState. `debate_impl` is required for a
    cycle to pass the debate node (WP3 CP2) — tests inject a double, production the real machinery."""
    app = build_deep_loop(event_log, fault, checkpoint_path, debate_impl=debate_impl)
    state = initial or new_cycle_state()
    config = {"configurable": {"thread_id": state.cycle_id}}
    final = app.invoke(state, config=config)
    return CycleState.model_validate(final)
