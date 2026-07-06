#!/usr/bin/env bash
# vm_git_sync.sh — self-update the VM checkout to the gated remote head before a scheduled run.
# Runs as ExecStartPre of the hedgefund systemd services. Akshar never logs in; this keeps the
# always-on VM (clawbot-v2, /root/hedgefund) on reviewed code without manual pulls.
#
# SAFE + non-blocking by design:
#   - Only TRACKED files move. The gitignored var/ PIT store, event_log.json, and .env are untouched.
#   - A fetch/reset failure (transient network, etc.) does NOT abort the run — the job proceeds on
#     the current checkout and re-syncs next time, so a blip never skips a soak night.
#   - Idempotent: a no-op when already at origin/<branch>.
#   - QUEUE-PRESERVING (2026-07-05): queued vm( results commits awaiting delivery are REBASED onto
#     the new head, never reset away; any foreign commit still triggers the full reset (incident
#     protection unweakened). See the block below.
set -uo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
BRANCH="${AXRZCE_BRANCH:-main}"

cd "$REPO" || { echo "[vm-git-sync] repo $REPO missing — skipping sync"; exit 0; }

# Keep the vendor-data commit guard active on the VM too.
git config core.hooksPath ops/git-hooks 2>/dev/null || true

if ! git fetch --prune origin 2>/dev/null; then
  echo "[vm-git-sync] fetch failed — running current checkout $(git rev-parse --short HEAD 2>/dev/null)"
  exit 0
fi

# ── QUEUE-PRESERVING SYNC (2026-07-05 weekend finding) ──────────────────────────────────────────
# reset --hard used to ORPHAN queued vm( results commits awaiting delivery: nightly-window push
# failures left them queued, and the NEXT run's sync wiped them before its queued-push could
# deliver — the night_20260702 stranding class, made systematic (3 of 4 weekend records orphaned).
# If everything ahead of origin/<branch> is this repo's own vm( results commits, REBASE them onto
# the new head so the queue survives the sync. ANY foreign commit present → reset --hard exactly
# as before: the 2026-07-02 incident protection (a checkout must never keep unreviewed code ahead
# of the merge gate) is deliberately UNWEAKENED.
QUEUED=$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 0)
FOREIGN=$(git log --format='%h %s' "origin/$BRANCH..HEAD" 2>/dev/null | grep -cv '^[0-9a-f]* vm(' || true)
if [ "${QUEUED:-0}" -gt 0 ] && [ "${FOREIGN:-0}" -eq 0 ]; then
  if git rebase "origin/$BRANCH" 2>/dev/null; then
    echo "[vm-git-sync] rebased ${QUEUED} queued vm( commit(s) onto origin/$BRANCH @ $(git rev-parse --short "origin/$BRANCH")"
  else
    git rebase --abort 2>/dev/null || true
    echo "[vm-git-sync] rebase failed — running current checkout $(git rev-parse --short HEAD 2>/dev/null) (queued vm( commits kept)"
  fi
  exit 0
fi

if git reset --hard "origin/$BRANCH" 2>/dev/null; then
  echo "[vm-git-sync] synced to origin/$BRANCH @ $(git rev-parse --short HEAD)"
else
  echo "[vm-git-sync] reset failed — running current checkout $(git rev-parse --short HEAD 2>/dev/null)"
fi
exit 0
