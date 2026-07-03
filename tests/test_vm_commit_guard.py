"""The 2026-07-02 guard (incident ruling, Condition A) — red tests for ops/vm_commit_results.sh.

Drives the REAL script against throwaway git repos (a local bare 'origin' + a working clone):
  (1) the push goes ONLY to the checkout's current branch;
  (2) a checkout carrying non-results commits not on origin/main is REFUSED (exit 1) — a results
      push can never again carry code past the merge gate.

Gut map: set FOREIGN=0 in the script (disable the check) → the code-carrying checkout pushes →
test_refuses_when_head_carries_code red.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "ops" / "vm_commit_results.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout.strip()


def _mk_repos(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", str(origin), str(work)], capture_output=True, check=True)
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "checkout", "-b", "main")
    (work / "base.txt").write_text("base")
    _git(work, "add", "."); _git(work, "commit", "-m", "base")
    _git(work, "push", "-u", "origin", "main")
    return origin, work


def _run_script(work: Path, label: str = "test") -> subprocess.CompletedProcess:
    return subprocess.run([BASH, str(SCRIPT), label], cwd=work, capture_output=True, text=True,
                          env={**__import__("os").environ, "AXRZCE_REPO": str(work)})


def _origin_head(origin: Path, branch: str = "main") -> str:
    return _git(origin, "rev-parse", branch)


def test_results_only_commit_pushes_to_current_branch(tmp_path):
    origin, work = _mk_repos(tmp_path)
    (work / "results").mkdir()
    (work / "results" / "night.json").write_text("{}")
    r = _run_script(work)
    assert r.returncode == 0 and "pushed" in r.stdout
    assert "-> main" in r.stdout
    assert "vm(test)" in _git(origin, "log", "-1", "--format=%s", "main")


def test_refuses_when_head_carries_code(tmp_path):
    """THE incident shape: the checkout sits ahead of origin/main with a CODE commit; a results
    push must REFUSE (exit 1) — never carry the code past the gate. Gut the check → it pushes →
    this test is the red."""
    origin, work = _mk_repos(tmp_path)
    before = _origin_head(origin)
    (work / "code.py").write_text("print('unreviewed')")
    _git(work, "add", "."); _git(work, "commit", "-m", "wp999: unreviewed feature code")
    (work / "results").mkdir()
    (work / "results" / "night.json").write_text("{}")
    r = _run_script(work)
    assert r.returncode == 1, f"expected refusal, got rc={r.returncode}: {r.stdout}"
    assert "REFUSED" in r.stdout and "merge gate" in r.stdout
    assert _origin_head(origin) == before  # origin/main did not move


def test_own_prior_results_commits_are_allowed(tmp_path):
    """A queued (unpushed) vm( results commit must not block the next results push."""
    origin, work = _mk_repos(tmp_path)
    (work / "results").mkdir()
    (work / "results" / "a.json").write_text("{}")
    _git(work, "add", "results"); _git(work, "commit", "-m", "vm(prior): result artifacts queued")
    (work / "results" / "b.json").write_text("{}")
    r = _run_script(work)
    assert r.returncode == 0 and "pushed" in r.stdout


def test_pushes_to_a_feature_branch_not_main_when_checked_out_there(tmp_path):
    """Guard (1): the push target is the CURRENT branch — a branch checkout can never move main."""
    origin, work = _mk_repos(tmp_path)
    main_before = _origin_head(origin)
    _git(work, "checkout", "-b", "wp-test")
    _git(work, "push", "-u", "origin", "wp-test")
    (work / "results").mkdir()
    (work / "results" / "x.json").write_text("{}")
    r = _run_script(work)
    assert r.returncode == 0 and "-> wp-test" in r.stdout
    assert _origin_head(origin) == main_before                 # main untouched
    assert "vm(test)" in _git(origin, "log", "-1", "--format=%s", "wp-test")


def test_detached_head_refused(tmp_path):
    origin, work = _mk_repos(tmp_path)
    _git(work, "checkout", "--detach")
    (work / "results").mkdir()
    (work / "results" / "x.json").write_text("{}")
    r = _run_script(work)
    assert r.returncode == 1 and "detached" in r.stdout


def test_noop_when_nothing_new(tmp_path):
    _, work = _mk_repos(tmp_path)
    r = _run_script(work)
    assert r.returncode == 0 and "no-op" in r.stdout


# ── the 2026-07-03 self-healing (the night_20260702 stranding can never recur) ──────


def _run_script_fast(work: Path, label: str = "test") -> subprocess.CompletedProcess:
    """Run with zero retry sleeps so failure paths are test-fast."""
    env = {**__import__("os").environ, "AXRZCE_REPO": str(work), "VM_PUSH_RETRY_SLEEPS": "0 0"}
    return subprocess.run([BASH, str(SCRIPT), label], cwd=work, capture_output=True, text=True,
                          env=env)


def _break_remote(work: Path) -> str:
    url = _git(work, "remote", "get-url", "origin")
    _git(work, "remote", "set-url", "origin", str(work / "nonexistent.git"))
    return url


def test_push_failure_retries_then_queues(tmp_path):
    """Simulated push failure: 3 attempts, then the commit stays QUEUED (exit 0 — the artifact is
    safe locally; the next invocation delivers it)."""
    _, work = _mk_repos(tmp_path)
    _break_remote(work)
    (work / "results").mkdir()
    (work / "results" / "night.json").write_text("{}")
    r = _run_script_fast(work)
    assert r.returncode == 0
    assert r.stdout.count("push attempt") == 3 or "attempt 3 failed" in r.stdout
    assert "QUEUED" in r.stdout
    assert "vm(test)" in _git(work, "log", "-1", "--format=%s")  # committed locally


def test_next_invocation_pushes_the_queued_commit(tmp_path):
    """THE night_20260702 gap, closed: with NOTHING new to commit, a queued vm( commit is still
    pushed on the next invocation. Gut the queued-push → 'no-op' strands it again → red."""
    origin, work = _mk_repos(tmp_path)
    url = _break_remote(work)
    (work / "results").mkdir()
    (work / "results" / "night.json").write_text("{}")
    _run_script_fast(work)                                   # commit queued, push failed
    _git(work, "remote", "set-url", "origin", url)           # remote heals
    r = _run_script_fast(work)                               # NOTHING new this time
    assert r.returncode == 0 and "pushed" in r.stdout
    assert "vm(test)" in _git(origin, "log", "-1", "--format=%s", "main")


def test_foreign_commit_refused_in_the_queued_push_path_too(tmp_path):
    """A queued vm( commit plus a foreign code commit must refuse — in EVERY path."""
    origin, work = _mk_repos(tmp_path)
    before = _origin_head(origin)
    url = _break_remote(work)
    (work / "results").mkdir()
    (work / "results" / "night.json").write_text("{}")
    _run_script_fast(work)                                   # queued vm( commit
    (work / "sneak.py").write_text("code")
    _git(work, "add", "."); _git(work, "commit", "-m", "sneaky code commit")
    _git(work, "remote", "set-url", "origin", url)
    r = _run_script_fast(work)
    assert r.returncode == 1 and "REFUSED" in r.stdout
    assert _origin_head(origin) == before
