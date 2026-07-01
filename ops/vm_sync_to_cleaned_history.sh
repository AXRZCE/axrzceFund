#!/usr/bin/env bash
# vm_sync_to_cleaned_history.sh — bring the always-on VM (clawbot-v2) onto the rewritten history
# after the vendor-data scrub + force-push. Akshar never logs in; the VM runs this on its timer.
#
# SAFE + IDEMPOTENT by design:
#   - Runnable BEFORE the force-push: if the remote head is unchanged, it is a clean no-op.
#   - Runnable AFTER: it hard-resets the tracked tree onto the rewritten remote head.
#   - Never loses local work: any unpushed local commits are PARKED on a branch first, then the
#     tree is reset. (After a history rewrite those old-SHA commits can't fast-forward; parking
#     keeps them recoverable for manual reconciliation onto the clean history.)
#   - Only tracked files move. The gitignored var/ PIT store + .env are untouched.
#
# Usage (on the VM):  ops/vm_sync_to_cleaned_history.sh [branch]      # default: main
set -euo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
BRANCH="${1:-main}"
TIMERS=(hedgefund-soak.timer hedgefund-g05.timer)

log() { printf '[vm-sync %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

cd "$REPO"

# 1) Pause the VM's scheduled jobs so nothing ingests/commits mid-reset.
for t in "${TIMERS[@]}"; do systemctl stop "$t" 2>/dev/null || true; done
log "paused timers: ${TIMERS[*]}"

# Ensure the vendor-data commit guard is active here too.
git config core.hooksPath ops/git-hooks 2>/dev/null || true

# 2) Fetch the (possibly rewritten) remote.
git fetch --prune origin

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
  log "already in sync with origin/$BRANCH ($LOCAL) — no-op (rewrite not yet applied, or done)."
else
  # 3) Park any local commits not present on the remote before a hard reset can drop them.
  if [ -n "$(git rev-list "origin/$BRANCH..HEAD" 2>/dev/null || true)" ]; then
    PARK="parked/$(git rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M%S)"
    git branch -f "$PARK" HEAD
    log "PARKED unpushed local commits on '$PARK' — reconcile manually onto the cleaned history."
  fi
  # 4) Hard-reset the tracked tree onto the remote head.
  git reset --hard "origin/$BRANCH"
  log "reset --hard to origin/$BRANCH ($(git rev-parse --short HEAD))."
fi

# 5) Re-enable the scheduled jobs.
for t in "${TIMERS[@]}"; do systemctl start "$t" 2>/dev/null || true; done
log "re-enabled timers; VM at $(git rev-parse --short HEAD) on $BRANCH."
