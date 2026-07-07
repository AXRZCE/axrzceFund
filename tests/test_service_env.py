"""Defect-1 guard (2026-07-07): every systemd unit that RUNS A COMMAND must resolve HOME=/root.

Root cause (docs/incidents/2026-07-02-vm-push-bypass.md, Addendum 2026-07-07): the systemd service
context sets no HOME, so git's credential.helper=store could not find /root/.git-credentials and
every nightly `git push` failed with "could not read Username" from night_20260702 onward — the
Monday 2026-07-06 record among the stranded. The fix is Environment=HOME=/root on all four service
units.

This test is the backstop: any unit under deploy/systemd/ that runs a command (has an Exec*
directive in [Service]) but does not RESOLVE HOME=/root goes red here — before it can strand
another night's record. It globs every unit file, not just *.service, so a future non-.service
unit that ever gains an ExecStart is covered too; and it resolves Environment= the way systemd
does (last value wins, a bare `Environment=` clears) so an override or reset-after-set cannot
false-green.

Gut map: delete the `Environment=HOME=/root` line from any command-running unit -> red.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

UNIT_DIR = Path(__file__).resolve().parent.parent / "deploy" / "systemd"
_EXEC_KEYS = ("ExecStart", "ExecStartPre", "ExecStartPost", "ExecStop", "ExecStopPost", "ExecReload")


def _service_lines(text: str) -> list[str]:
    """The directive lines inside the [Service] section (blank/comment/other-section lines dropped)."""
    out: list[str] = []
    section: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "Service":
            out.append(line)
    return out


def _runs_a_command(text: str) -> bool:
    return any(line.split("=", 1)[0].strip() in _EXEC_KEYS for line in _service_lines(text))


def _resolved_environment(text: str) -> dict[str, str]:
    """Resolve [Service] Environment= the way systemd does: assignments accumulate in order, a later
    KEY overrides an earlier one, and a bare `Environment=` (empty value) clears everything set so
    far. shlex parses double-quoted values (incl. spaces). Returns the final {VAR: VALUE}."""
    env: dict[str, str] = {}
    for line in _service_lines(text):
        if not line.startswith("Environment="):
            continue
        payload = line[len("Environment=") :].strip()
        if payload == "":
            env.clear()  # systemd: a bare Environment= unsets all previously-set variables
            continue
        for token in shlex.split(payload):
            if "=" in token:
                key, value = token.split("=", 1)
                env[key] = value
    return env


def _unit_files() -> list[Path]:
    return sorted(p for p in UNIT_DIR.iterdir() if p.is_file())


COMMAND_UNITS = [p for p in _unit_files() if _runs_a_command(p.read_text(encoding="utf-8"))]


def test_units_discovered():
    """Fail loudly rather than silently pass if discovery finds nothing (path drift / bad checkout)."""
    services = [p for p in _unit_files() if p.suffix == ".service"]
    assert services, f"no *.service units found under {UNIT_DIR}"
    assert COMMAND_UNITS, f"no command-running units found under {UNIT_DIR}"


@pytest.mark.parametrize("unit", COMMAND_UNITS, ids=lambda p: p.name)
def test_command_unit_resolves_home_root(unit: Path):
    """Defect-1: HOME must RESOLVE to /root so git's store credential helper is reachable."""
    home = _resolved_environment(unit.read_text(encoding="utf-8")).get("HOME")
    assert home == "/root", (
        f"{unit.name} runs a command but HOME resolves to {home!r}, not '/root' — systemd sets no "
        f"HOME, so git credential.helper=store cannot read /root/.git-credentials and the push "
        f"fails with 'could not read Username' (Defect-1; docs/incidents/2026-07-02-vm-push-bypass.md)."
    )
