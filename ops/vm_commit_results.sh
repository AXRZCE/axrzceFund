#!/usr/bin/env bash
# vm_commit_results.sh — commit the just-produced result artifacts (our OWN outputs) to the tracked
# results/ path and push (non-force). Runs as ExecStopPost of the hedgefund services.
#
# SAFE by design:
#   - Stages ONLY results/ + data/fixtures/locks/ — never var/. The pre-commit vendor guard is the
#     backstop for anything mis-shaped.
#   - Non-force push; a push race defers to the next run. Idempotent when nothing is new.
#
# ── THE 2026-07-02 GUARD (incident: docs/incidents/2026-07-02-vm-push-bypass.md) ────────────────
# A results push once fast-forwarded origin/main to an unreviewed feature-branch head, because this
# script pushed to $BRANCH (default main) from a checkout that vm_git_sync had reset onto a branch.
# Permanent closure, both conditions enforced HERE (red-tested in tests/test_vm_commit_guard.py):
#   (1) push ONLY to the checkout's CURRENT branch — never an env-configured other ref;
#   (2) REFUSE OUTRIGHT (exit 1, loud) if HEAD carries any commit not on origin/main that is not
#       one of this script's own results commits (message prefix "vm(") — a results push can never
#       again carry code past the merge gate.
set -uo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
LABEL="${1:-run}"

cd "$REPO" || { echo "[vm-commit-results] repo $REPO missing"; exit 0; }
git config core.hooksPath ops/git-hooks 2>/dev/null || true

# (1) the push target is the CURRENT branch, full stop.
CURRENT=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -z "$CURRENT" ] || [ "$CURRENT" = "HEAD" ]; then
  echo "[vm-commit-results] REFUSED: detached HEAD — no push target (guard 2026-07-02)"; exit 1
fi

# (2) no unreviewed code may ride a results push: every local commit ahead of origin/main must be
# one of this script's own "vm(" results commits. Fetch best-effort; the last-known origin/main
# ref is used if the fetch fails (the check still runs — fail closed, not open).
git fetch origin main 2>/dev/null || true
FOREIGN=$(git log --format='%h %s' origin/main..HEAD 2>/dev/null | grep -cv '^[0-9a-f]* vm(' || true)
if [ "${FOREIGN:-0}" -gt 0 ]; then
  echo "[vm-commit-results] REFUSED: HEAD carries ${FOREIGN} non-results commit(s) not on"
  echo "  origin/main — a results push must NEVER carry code past the merge gate."
  echo "  (guard 2026-07-02; see docs/incidents/2026-07-02-vm-push-bypass.md)"
  git log --oneline origin/main..HEAD | head -10
  exit 1
fi

# separate adds: a missing pathspec in a combined add silently stages NOTHING (caught by the tests)
git add results/ 2>/dev/null || true
git add data/fixtures/locks/ 2>/dev/null || true
if git diff --cached --quiet 2>/dev/null; then
  echo "[vm-commit-results] nothing new in results/ — no-op"
  exit 0
fi

if ! git commit -q -m "vm(${LABEL}): result artifacts $(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
  echo "[vm-commit-results] commit blocked/failed (guard?) — not pushing"
  exit 0
fi

# Integrate any remote advance so the non-force push fast-forwards; abort a stray rebase on conflict
# (next run's ExecStartPre reset --hard cleans up).
git pull --rebase origin "$CURRENT" 2>/dev/null || git rebase --abort 2>/dev/null || true
if git push origin "HEAD:$CURRENT" 2>/dev/null; then
  echo "[vm-commit-results] pushed $(git rev-parse --short HEAD) -> $CURRENT"
else
  echo "[vm-commit-results] push deferred (non-fast-forward/offline) — retries next run"
fi
exit 0
