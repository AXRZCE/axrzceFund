"""WP1 zero-LLM-spend gate, two ways (brief §5 WP1):
(a) static — no LLM SDK import anywhere under graphs/;
(b) dynamic — with the LLM SDKs monkeypatched to raise on use, a full cycle still
    completes, proving the skeleton never instantiates or calls an LLM client.
"""
import re
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LLM_IMPORT = re.compile(r"^[ \t]*(?:import|from)[ \t]+(anthropic|openai)\b", re.M)


def test_no_llm_sdk_import_under_graphs():
    leaks = []
    for p in (REPO / "graphs").rglob("*.py"):
        for m in LLM_IMPORT.finditer(p.read_text(encoding="utf-8")):
            leaks.append(f"{p.relative_to(REPO).as_posix()}: {m.group(0).strip()}")
    assert not leaks, "LLM SDK import under graphs/ (WP1 must be zero-LLM):\n" + "\n".join(leaks)


def test_cycle_runs_with_llm_clients_booby_trapped(tmp_path, monkeypatch):
    """Install fake anthropic/openai modules that raise if anything is accessed, then
    run a full cycle — it must complete, proving no LLM client is ever touched."""
    def _booby(name):
        mod = types.ModuleType(name)

        class _Raise:
            def __getattr__(self, _):
                raise AssertionError(f"WP1 skeleton must not use {name}")

            def __call__(self, *a, **k):
                raise AssertionError(f"WP1 skeleton must not call {name}")

        # any attribute access (e.g. anthropic.Anthropic) raises
        mod.__getattr__ = lambda _attr: (_ for _ in ()).throw(  # type: ignore
            AssertionError(f"WP1 skeleton must not use {name}"))
        return mod

    monkeypatch.setitem(sys.modules, "anthropic", _booby("anthropic"))
    monkeypatch.setitem(sys.modules, "openai", _booby("openai"))

    from core.event_log import EventLog
    from graphs.deep_loop import run_cycle

    el = EventLog(tmp_path / "ev.db")
    final = run_cycle(el, checkpoint_path=tmp_path / "ck.sqlite")
    assert not final.halted and final.decision["action"] == "intended_order"
