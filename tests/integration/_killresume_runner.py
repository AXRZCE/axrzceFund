"""Subprocess target for the kill-resume test (R7). Runs the deep loop up to the
interrupt-before-`pm` (so nodes through `ballot` are checkpointed and `pm` has not
run), signals 'ready', then blocks alive until the parent SIGKILLs it. Not a test
(underscore prefix) — invoked as `python _killresume_runner.py <args>`.
"""
import sys
import time
from pathlib import Path

from core.event_log import EventLog
from graphs.deep_loop import build_deep_loop
from graphs.state import CycleState


def main() -> None:
    ev_db, ck, state_json, ready = sys.argv[1:5]
    el = EventLog(Path(ev_db))
    state = CycleState.model_validate_json(Path(state_json).read_text(encoding="utf-8"))
    app = build_deep_loop(el, checkpoint_path=Path(ck), interrupt_before=["pm"])
    # Runs cycle_open..ballot, persists the checkpoint, returns at the interrupt.
    app.invoke(state, config={"configurable": {"thread_id": state.cycle_id}})
    Path(ready).write_text("ready", encoding="utf-8")  # checkpoint exists; pm not run
    time.sleep(3600)  # block alive until SIGKILLed (uncatchable)


if __name__ == "__main__":
    main()
