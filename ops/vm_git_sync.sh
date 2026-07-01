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
if git reset --hard "origin/$BRANCH" 2>/dev/null; then
  echo "[vm-git-sync] synced to origin/$BRANCH @ $(git rev-parse --short HEAD)"
else
  echo "[vm-git-sync] reset failed — running current checkout $(git rev-parse --short HEAD 2>/dev/null)"
fi
exit 0
