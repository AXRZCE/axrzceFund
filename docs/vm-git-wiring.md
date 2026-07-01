# VM git wiring — autonomous self-update + result-commit (clawbot-v2)

Akshar never logs into the VM. This wires the always-on VM (`/root/hedgefund`) so that every
scheduled run **pulls the gated code first** and **commits its own proof after**, with no manual
step after a single one-time bootstrap.

## What runs each night
The systemd services (`deploy/systemd/hedgefund-*.service`) wrap the existing entrypoints with:
- `ExecStartPre=ops/vm_git_sync.sh` — `git fetch && git reset --hard origin/main` in
  `/root/hedgefund`. Only tracked files move; the gitignored `var/` PIT store, `event_log.json`,
  and `.env` are untouched. Non-blocking: a network blip runs the current checkout and re-syncs
  next time, so a soak night is never skipped.
- `ExecStart=` — the real job (`ops/nightly_ingest.py` for the soak / `ops/broker_roundtrip.py`
  for the drill).
- `ExecStopPost=ops/vm_commit_results.sh <label>` — stage **only** `results/`, commit, and push
  non-force. Runs regardless of the job's exit code, so deviation/failed nights still record a
  proof. The pre-commit guard is the backstop against vendor data ever reaching `results/`.

The G0.3 soak summary (`results/soak/night_*.json`) and G0.5 drill (`results/g05/*.json`) are our
own outputs — row **counts**/statuses/flags and orders/fills — not licensed vendor rows. Reports,
orders, and fills commit normally (per the owner ruling); the raw vendor data stays in the
gitignored PIT store.

## One-time bootstrap (run once, as root)
```bash
cd /root/hedgefund
git fetch origin && git reset --hard origin/main   # pull the units + scripts + guard
sudo bash ops/vm_bootstrap.sh                       # install units, daemon-reload, enable soak timer
```
`vm_bootstrap.sh` is idempotent: it activates the commit guard (`core.hooksPath`), installs the
four units into `/etc/systemd/system/`, migrates any existing `var/` proofs into `results/`,
enables the **recurring soak timer** (not the g05 one — G0.5 already passed), and commits the
migrated proofs. Re-run it after any unit-file change lands in git.

## Verify off-box (no VM login)
After the next 21:30 ET soak run, confirm from GitHub:
```bash
git fetch origin && git log --oneline origin/main | grep "vm(soak)"   # the VM's committed proof
git show origin/main:results/soak/$(git ls-tree --name-only origin/main results/soak | tail -1 | xargs basename)
```
A `vm(soak): result artifacts …` commit on `origin/main` authored by the VM, with a fresh
`results/soak/night_*.json`, is the committed evidence that the VM synced, ran, and reported.

## Notes / limits
- **Untested on the VM until the first bootstrap** — the units are authored from
  `docs/vm-soak-setup.md`'s "AS DEPLOYED" spec (Type=oneshot, WorkingDirectory=/root/hedgefund,
  TimeoutStartSec=1800, Persistent=true, OnCalendar in America/New_York). Verify the first run in
  the journal (`journalctl -u hedgefund-soak.service`).
- If the deployed checkout is **not** `/root/hedgefund`, pass `AXRZCE_REPO=/path` (the scripts read
  it) and adjust `WorkingDirectory=`/`ExecStart=` in the unit files.
- A push race just defers one run; the artifact is on disk and re-commits next time.
- `ops/vm_sync_to_cleaned_history.sh` remains the heavier one-time tool for a **history rewrite**
  (pauses timers, parks unpushed commits, hard-resets) — distinct from the nightly `vm_git_sync.sh`.
