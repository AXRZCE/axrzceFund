"""WP3 CP1b guard (item 8a): agent-output writers must resolve to gitignored/out-of-tree dirs, never
the tracked working tree. Anti-hoax for the data-governance policy — kills the Path("")-is-truthy class
that let 23 licensed-figure memos land in the repo root. Delete the check -> a tracked dir is accepted
-> these go red."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.agent_output import UnsafeOutputDir, is_gitignored, safe_agent_output_dir

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()).resolve()


def test_empty_preferred_uses_fallback_not_cwd():
    # the Path("")-is-truthy bug: an empty preferred must NOT resolve to '.' / the repo root
    d = safe_agent_output_dir("", fallback="var/cp1_memos")
    assert d != ROOT
    assert is_gitignored(d)


def test_none_preferred_uses_fallback():
    d = safe_agent_output_dir(None, fallback="var/cp1_memos")
    assert is_gitignored(d)


def test_tracked_dir_is_refused():
    # docs/ is tracked and not gitignored -> must fail closed
    with pytest.raises(UnsafeOutputDir):
        safe_agent_output_dir("docs", fallback="var/cp1_memos")


def test_repo_root_is_refused():
    with pytest.raises(UnsafeOutputDir):
        safe_agent_output_dir(str(ROOT), fallback="var/cp1_memos")


def test_gitignored_dir_allowed():
    d = safe_agent_output_dir("var/cp1_memos", fallback="var/other")
    assert is_gitignored(d)
    assert (ROOT in d.parents) or (d == ROOT / "var" / "cp1_memos")
