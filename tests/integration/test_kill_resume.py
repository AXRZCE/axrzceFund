"""WP1 kill-and-resume proof (R7) — Linux/VM only (real SIGKILL).

Properties (docs/wp1-skeleton-done-criteria.md R7):
  1. Real kill, real process — a subprocess takes an uncatchable SIGKILL.
  2. Killed mid-cycle after a checkpoint — interrupt_before `pm`: `ballot` checkpointed,
     `pm` not run (ballot_cast present, proposal_written absent).
  3. Resume proves it resumed — pre-kill events appear EXACTLY ONCE (continued, did
     not restart/duplicate) AND the final replay_comparable() (incl. decision_ts)
     equals an un-killed run's.

Gated @pytest.mark.integration; skipped where SIGKILL is unavailable (Windows).
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.event_log import EventLog
from graphs.deep_loop import build_deep_loop, new_cycle_state, run_cycle
from graphs.state import CycleState

pytestmark = pytest.mark.integration

_RUNNER = Path(__file__).parent / "_killresume_runner.py"


def _types(el: EventLog, cycle_id: str) -> list[str]:
    return [e.event_type for e in el.get_events(cycle_id=cycle_id)]


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"),
                    reason="SIGKILL requires POSIX — run on the Linux VM")
def test_kill_resume_continues_from_checkpoint(tmp_path):
    state = new_cycle_state()
    state_json = tmp_path / "state.json"
    state_json.write_text(state.model_dump_json(), encoding="utf-8")
    ev, ck, ready = tmp_path / "ev.db", tmp_path / "ck.sqlite", tmp_path / "ready"

    # Reference: a clean, un-killed run from the SAME initial state.
    ref = run_cycle(EventLog(tmp_path / "refev.db"), checkpoint_path=tmp_path / "refck.sqlite",
                    initial=state.model_copy(deep=True))
    assert ref.decision and ref.decision["action"] == "intended_order"

    # (1) subprocess runs to interrupt-before-pm, signals ready, blocks.
    proc = subprocess.Popen([sys.executable, str(_RUNNER),
                             str(ev), str(ck), str(state_json), str(ready)])
    try:
        for _ in range(600):
            if ready.exists():
                break
            time.sleep(0.1)
        assert ready.exists(), "subprocess never reached the interrupt"
        os.kill(proc.pid, signal.SIGKILL)  # (1) real, uncatchable kill
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)

    # (2) killed mid-cycle: ballot checkpointed, pm did NOT run.
    el = EventLog(ev)
    pre = _types(el, state.cycle_id)
    assert "ballot_cast" in pre
    assert "proposal_written" not in pre and "intended_order" not in pre

    # (3) resume from the on-disk checkpoint in this fresh process (killed proc is dead).
    app = build_deep_loop(el, checkpoint_path=ck)
    final = CycleState.model_validate(
        app.invoke(None, config={"configurable": {"thread_id": state.cycle_id}}))

    # (3a) exactly-once → it CONTINUED past the checkpoint (no restart, no duplicate).
    post = _types(el, state.cycle_id)
    assert post.count("memo_written") == 3, post
    assert post.count("ballot_cast") == 3, post  # 3 not 6 → did not restart
    assert post.count("proposal_written") == 1, post
    assert post.count("intended_order") == 1, post

    # (3b) final matches the clean run, decision_ts included.
    assert not final.halted
    assert final.replay_comparable() == ref.replay_comparable()
