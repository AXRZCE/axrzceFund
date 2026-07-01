"""WP1 deep-loop skeleton tests (laptop-runnable). The real-SIGKILL kill-and-resume
proof requires Linux and lives in tests/integration/test_kill_resume.py (run on the VM).
"""
import re
from pathlib import Path

from core.event_log import EventLog
from graphs.deep_loop import FaultInjector, new_cycle_state, run_cycle

REPO = Path(__file__).resolve().parent.parent


def _types(el: EventLog, cycle_id: str) -> list[str]:
    return [e.event_type for e in el.get_events(cycle_id=cycle_id)]


def test_clean_cycle_emits_intended_order(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    final = run_cycle(el, checkpoint_path=tmp_path / "ck.sqlite")
    assert not final.halted
    assert final.decision and final.decision["action"] == "intended_order"
    assert len(final.completed_nodes) == 10
    assert "intended_order" in _types(el, final.cycle_id)
    assert final.failure is None


def test_replay_reproduces_same_cycle(tmp_path):
    """R2: re-invoking the SAME initial state reproduces identical decision content,
    and the excluded trade_id genuinely differs (so the exclusion is load-bearing)."""
    state0 = new_cycle_state()
    f1 = run_cycle(EventLog(tmp_path / "e1.db"), checkpoint_path=tmp_path / "c1.sqlite",
                   initial=state0.model_copy(deep=True))
    f2 = run_cycle(EventLog(tmp_path / "e2.db"), checkpoint_path=tmp_path / "c2.sqlite",
                   initial=state0.model_copy(deep=True))
    assert f1.replay_comparable() == f2.replay_comparable()
    assert f1.decision["trade_id"] != f2.decision["trade_id"]  # the excluded field varied


def test_fail_closed_halts_with_no_decision(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    final = run_cycle(el, fault=FaultInjector("pm"), checkpoint_path=tmp_path / "ck.sqlite")
    assert final.halted and final.failure["node"] == "pm"
    assert final.decision is None  # R5: NO decision/order event on failure
    types = _types(el, final.cycle_id)
    assert "cycle_failed" in types and "intended_order" not in types
    # R4: downstream nodes did not run
    assert "risk_gate" not in final.completed_nodes
    assert "terminal" not in final.completed_nodes


def test_fail_closed_at_terminal_emits_no_order(tmp_path):
    """A failure at the terminal node itself must still leave no intended_order event."""
    el = EventLog(tmp_path / "ev.db")
    final = run_cycle(el, fault=FaultInjector("terminal"), checkpoint_path=tmp_path / "ck.sqlite")
    assert final.halted and final.failure["node"] == "terminal"
    assert "intended_order" not in _types(el, final.cycle_id)


def test_llm_error_from_agent_fails_closed(tmp_path):
    """An agent's LLMError (e.g. after the metered client exhausts retries on empty/degenerate
    responses) propagates to the deep-loop's fail-closed router exactly like any node exception:
    the cycle halts, logs cycle_failed, runs no downstream node, and emits NO decision — no trade
    that cycle, no crash."""
    from core.llm import LLMError
    el = EventLog(tmp_path / "ev.db")
    final = run_cycle(el, fault=FaultInjector("research", exc=LLMError),
                      checkpoint_path=tmp_path / "ck.sqlite")
    assert final.halted and final.failure["node"] == "research"
    assert final.decision is None  # no trade this cycle
    types = _types(el, final.cycle_id)
    assert "cycle_failed" in types and "intended_order" not in types
    assert "verify" not in final.completed_nodes and "terminal" not in final.completed_nodes


def test_stubs_confined_to_quarantine():
    """R6/§0: graphs.stubs is imported only in graphs/stubs/ and graphs/deep_loop.py."""
    pat = re.compile(r"^[ \t]*(?:from|import)[ \t]+graphs\.stubs\b", re.M)
    allowed = ("graphs/stubs/", "graphs/deep_loop.py")
    leaks = []
    for d in ("core", "data", "harness", "graphs", "agents", "ops", "tests"):
        root = REPO / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            rel = p.relative_to(REPO).as_posix()
            if rel.startswith(allowed):
                continue
            if pat.search(p.read_text(encoding="utf-8")):
                leaks.append(rel)
    assert not leaks, f"graphs.stubs imported outside quarantine: {leaks}"
