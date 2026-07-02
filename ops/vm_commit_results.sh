#!/usr/bin/env bash
# vm_commit_results.sh — commit the just-produced result artifacts (our OWN outputs: the G0.3 soak
# night summary / the G0.5 broker drill JSON) to the tracked results/ path and push (non-force).
# Runs as ExecStopPost of the hedgefund services, so even a deviation/failed night still records
# its proof. Akshar reads these off GitHub without logging into the VM.
#
# SAFE by design:
#   - Stages ONLY results/ — never var/ (gitignored raw vendor data). The pre-commit guard is the
#     backstop: if vendor-shaped data ever lands in results/, the commit is blocked, not pushed.
#   - Non-force push; integrates any remote advance with --rebase first. A push race just defers to
#     the next run (the artifact is already on disk and will re-commit).
#   - Idempotent: a no-op when there is nothing new to commit.
set -uo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
BRANCH="${AXRZCE_BRANCH:-main}"
LABEL="${1:-run}"

cd "$REPO" || { echo "[vm-commit-results] repo $REPO missing"; exit 0; }
git config core.hooksPath ops/git-hooks 2>/dev/null || true

# results/ + the fixture hash-locks (committed-by-design metadata; WP6 clean-week criterion 3).
# The vendor guard remains the backstop for anything mis-shaped.
git add results/ data/fixtures/locks/ 2>/dev/null || true
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
git pull --rebase origin "$BRANCH" 2>/dev/null || git rebase --abort 2>/dev/null || true
if git push origin "$BRANCH" 2>/dev/null; then
  echo "[vm-commit-results] pushed $(git rev-parse --short HEAD)"
else
  echo "[vm-commit-results] push deferred (non-fast-forward/offline) — retries next run"
fi
exit 0
