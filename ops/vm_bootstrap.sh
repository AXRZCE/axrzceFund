#!/usr/bin/env bash
# vm_bootstrap.sh — ONE-TIME VM setup (run once as root). Installs the committed systemd units,
# activates the vendor-data commit guard, migrates any existing soak/g05 proofs into the tracked
# results/ path, and enables the recurring soak timer. Every night after is autonomous: each run
# self-updates via ExecStartPre (vm_git_sync.sh) and commits its proof via ExecStopPost
# (vm_commit_results.sh).
#
# Run:
#   cd /root/hedgefund
#   git fetch origin && git reset --hard origin/main
#   sudo bash ops/vm_bootstrap.sh
#
# PREREQ this script does NOT handle — a PUSH CREDENTIAL. The nightly result-commit
# (vm_commit_results.sh) pushes to origin; that needs, one time on the VM, either a PAT via a
# credential helper (`git config credential.helper store`, then one authenticated push to cache it)
# or an SSH deploy key with write access (remote set to the git@github.com: URL). Without it the
# result-commit is created locally but the push is rejected. See docs/vm-soak-setup.md.
#
# Idempotent: safe to re-run (e.g. after a unit-file change lands in git).
set -uo pipefail

REPO="${AXRZCE_REPO:-/root/hedgefund}"
cd "$REPO"

echo "== activate the vendor-data commit guard on the VM =="
git config core.hooksPath ops/git-hooks

echo "== set the VM bot's repo-local git identity (else result-commits fail: 'Author identity unknown') =="
git config user.email "vm-bot@axrzcefund.local"
git config user.name  "axrzceFund VM (clawbot-v2)"

echo "== install systemd units (copy; re-run this bootstrap after a unit-file change) =="
for u in hedgefund-soak.service hedgefund-soak.timer hedgefund-g05.service hedgefund-g05.timer \n         hedgefund-cycle.service hedgefund-cycle.timer; do  # cycle units INSTALLED, timer NOT enabled (R10)
  install -m 644 "$REPO/deploy/systemd/$u" "/etc/systemd/system/$u"
  echo "  installed $u"
done
systemctl daemon-reload

echo "== migrate existing proofs var/ -> results/ (best-effort, one-time) =="
mkdir -p results/soak results/g05
cp -n var/ingestion_logs/night_*.json results/soak/ 2>/dev/null || true
cp -n var/g05/*.json                   results/g05/  2>/dev/null || true

echo "== enable the RECURRING soak timer (g05 stays on-demand — G0.5 already passed) =="
systemctl enable --now hedgefund-soak.timer
systemctl --no-pager status hedgefund-soak.timer 2>/dev/null | head -4 || true
echo "  next soak run:"; systemctl list-timers hedgefund-soak.timer --no-pager 2>/dev/null | head -2 || true

echo "== commit any migrated proofs now =="
bash ops/vm_commit_results.sh bootstrap || true

echo "== bootstrap complete. VM @ $(git rev-parse --short HEAD); soak autonomous. =="
