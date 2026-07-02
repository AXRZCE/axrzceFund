"""Structural guard: agent-output files must never be written inside the tracked tree (WP3 CP1b).

Agent outputs (bull memos, judge records, etc.) quote licensed fixture figures, so in this PUBLIC repo
they must live ONLY in gitignored / out-of-tree locations. CP1b near-miss: a `Path("")`-is-truthy bug
wrote 23 licensed-figure memos to the repo root, and ops/precommit_guard.py would NOT have blocked them
(a memo carries no price_bars/fundamentals row arrays — only quoted values in claim text). The only
defense was noticing. This replaces vigilance with a committed invariant: every agent-output writer
resolves its directory through `safe_agent_output_dir`, which FAIL-CLOSES on an empty / cwd / tracked-
and-not-gitignored path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class UnsafeOutputDir(Exception):
    """An agent-output directory resolved inside the tracked tree — refused, fail-closed."""


def _repo_root() -> Path:
    return Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
    ).resolve()


def is_gitignored(path: Path | str) -> bool:
    """True if `path` is ignored by git (writing there cannot pollute the tracked tree). Works on
    paths that do not exist yet (git checks the ignore rules, not existence)."""
    return subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=_repo_root()
    ).returncode == 0


def safe_agent_output_dir(preferred: str | Path | None, *, fallback: str | Path) -> Path:
    """Resolve a directory safe for agent outputs that quote licensed figures, then create it.

    Safe = OUTSIDE the repo, OR gitignored. Fail-closed:
      - a blank/None `preferred` uses `fallback` (NOT the cwd — this kills the Path("")-is-truthy class);
      - a path inside the tracked tree that is not gitignored raises `UnsafeOutputDir`.
    Never silently writes into the tracked working tree.
    """
    raw = str(preferred).strip() if preferred is not None else ""
    cand = (Path(raw) if raw else Path(fallback)).resolve()
    root = _repo_root()
    if cand == root or root in cand.parents:
        if not is_gitignored(cand):
            raise UnsafeOutputDir(
                f"agent-output dir {cand} is inside the tracked tree and not gitignored — refusing "
                f"(licensed figures must never enter the public repo). Use a gitignored dir, e.g. var/."
            )
    cand.mkdir(parents=True, exist_ok=True)
    return cand
