#!/usr/bin/env bash
# vm_commit_results.sh — commit the just-produced result artifacts (our OWN outputs) to the tracked
# results/ path and push (non-force). Runs as ExecStopPost of the hedgefund services.
#
# SAFE by design:
#   - Stages ONLY results/ + data/fixtures/locks/ — never var/. The pre-commit vendor guard is the
#     backstop for anything mis-shaped.
#   - Non-force push. Idempotent when nothing is new AND nothing is queued.
#
# ── THE 2026-07-02 GUARD (incident: docs/incidents/2026-07-02-vm-push-bypass.md) ────────────────
#   (1) push ONLY to the checkout's CURRENT branch — never an env-configured other ref;
#   (2) REFUSE OUTRIGHT (exit 1, loud) if HEAD carries any commit not on origin/main that is not
#       one of this script's own results commits (message prefix "vm(") — a results push can never
#       carry code. The guard is RE-CHECKED before EVERY push attempt.
#
# ── SELF-HEALING (2026-07-03 hardening; the VM must never depend on a CC session) ───────────────
#   - QUEUED-PUSH: on EVERY invocation, if origin/main..HEAD already carries queued vm( results
#     commits (and nothing foreign), they are pushed even when there is nothing new to commit —
#     the no-op gap that stranded night_20260702 is closed.
#   - RETRY: a failed push retries up to 2 more times (3 attempts total), spaced by
#     $VM_PUSH_RETRY_SLEEPS (default "120 180" seconds — the observed ~01:41 UTC push flakiness is
#     transient). Still non-force; fetch + guard re-check + rebase before each attempt. Total
#     worst-case runtime fits the services' TimeoutStopSec.
#   - Exhausted retries leave the commits QUEUED; the next invocation's queued-push delivers them.
set -uo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
LABEL="${1:-run}"
RETRY_SLEEPS="${VM_PUSH_RETRY_SLEEPS:-120 180}"

cd "$REPO" || { echo "[vm-commit-results] repo $REPO missing"; exit 0; }
git config core.hooksPath ops/git-hooks 2>/dev/null || true

# (1) the push target is the CURRENT branch, full stop.
CURRENT=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -z "$CURRENT" ] || [ "$CURRENT" = "HEAD" ]; then
  echo "[vm-commit-results] REFUSED: detached HEAD — no push target (guard 2026-07-02)"; exit 1
fi

guard_check() {
  # (2) every local commit ahead of origin/main must be a "vm(" results commit — else refuse.
  git fetch origin main 2>/dev/null || true
  local foreign
  foreign=$(git log --format='%h %s' origin/main..HEAD 2>/dev/null | grep -cv '^[0-9a-f]* vm(' || true)
  if [ "${foreign:-0}" -gt 0 ]; then
    echo "[vm-commit-results] REFUSED: HEAD carries ${foreign} non-results commit(s) not on"
    echo "  origin/main — a results push must NEVER carry code past the merge gate."
    echo "  (guard 2026-07-02; see docs/incidents/2026-07-02-vm-push-bypass.md)"
    git log --oneline origin/main..HEAD | head -10
    return 1
  fi
  return 0
}

guard_check || exit 1

# separate adds: a missing pathspec in a combined add silently stages NOTHING (caught by the tests)
git add results/ 2>/dev/null || true
git add data/fixtures/locks/ 2>/dev/null || true
if ! git diff --cached --quiet 2>/dev/null; then
  if ! git commit -q -m "vm(${LABEL}): result artifacts $(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
    echo "[vm-commit-results] commit blocked/failed (guard?) — not pushing"
    exit 0
  fi
fi

# QUEUED-PUSH: anything ahead of origin/main (all vm( — the guard passed) must go, new or queued.
QUEUED=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
if [ "${QUEUED:-0}" -eq 0 ]; then
  echo "[vm-commit-results] nothing new and nothing queued — no-op"
  exit 0
fi

# RETRY loop: attempt, then one more per configured sleep. Guard re-checked before every attempt.
attempt=1
for delay in 0 $RETRY_SLEEPS; do
  [ "$delay" -gt 0 ] && { echo "[vm-commit-results] retry in ${delay}s"; sleep "$delay"; }
  guard_check || exit 1
  # integrate any remote advance so the non-force push fast-forwards; abort a stray rebase
  git pull --rebase origin "$CURRENT" 2>/dev/null || git rebase --abort 2>/dev/null || true
  if git push origin "HEAD:$CURRENT" 2>/dev/null; then
    echo "[vm-commit-results] pushed $(git rev-parse --short HEAD) -> $CURRENT (attempt $attempt)"
    exit 0
  fi
  echo "[vm-commit-results] push attempt $attempt failed"
  attempt=$((attempt + 1))
done
echo "[vm-commit-results] push deferred after $((attempt - 1)) attempts — commits stay QUEUED;"
echo "  the next invocation's queued-push delivers them (self-healing, 2026-07-03)"
exit 0
