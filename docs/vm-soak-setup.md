# VM Soak Setup — porting the nightly soak + G0.5 to the always-on VM

> **AS DEPLOYED (2026-06-15, authoritative) — read this before the runbook below.**
> The soak runs on the DigitalOcean Ubuntu 24.04 VM under **systemd timers**, NOT cron.
> Debian's `cron 3.0pl1` has unreliable `CRON_TZ`; systemd resolves named-TZ schedules
> DST-correctly and was verified with `systemd-analyze calendar`. Deployed units
> (isolated under `/root/hedgefund`, system Python 3.12, never touching ANTS):
> - `hedgefund-soak.{service,timer}` — `OnCalendar=*-*-* 21:30:00 America/New_York`
> - `hedgefund-g05.{service,timer}` — one-shot `OnCalendar=2026-06-16 10:00:00 America/New_York`
> - Both services: `Type=oneshot`, `WorkingDirectory=/root/hedgefund`,
>   `ExecStart=/root/hedgefund/.venv/bin/python ops/<entrypoint>`,
>   **`TimeoutStartSec=1800`** (hung-run self-heal) + **`Persistent=true`** (reboot
>   catch-up). These two directives are **load-bearing for the G0.3 counting rulings**
>   (validation-criteria.md G0.3): catch-up counts, timeout-kill does not.
> The **cron sections below are SUPERSEDED** — kept only as the original plan/history.
> The "prove the scheduler not the manual run" gate was met by a **timer-fired** proof
> (a throwaway timer triggering the real service), not a cron-fired one.

**Why:** the laptop cannot run the soak unattended (Modern Standby can't timer-wake;
the never-sleep power setting reverts across Windows updates). The always-on VM is the
reliable host. Moving to a Linux scheduler also retires the entire Windows scheduling
layer that produced the 5-day failure (`.cmd` wrappers + locale-date redirect bug).

**The lesson that governs this runbook:** "the pipeline works when I run it by hand"
proved nothing — the *scheduler* was the failure point. So the official soak clock
does **not** start until a **cron-fired** run lands clean. A manual run is necessary
but not sufficient.

---

## Constraints (owner-mandated — do not skip)

1. **Total isolation from ANTS.** Dedicated directory, own virtualenv, own `.env`.
   Touch nothing belonging to ANTS. Confirm no cron-name / port / filename / disk
   collision with whatever ANTS runs.
2. **Linux-native, cron-driven.** No `.cmd` wrappers (they were the killer bug and
   are not needed here). cron invokes `python ops/nightly_ingest.py` directly.
3. **Timezone is explicit and load-bearing.** Schedule in a *named* TZ
   (`America/New_York`), never the VM's local clock. The nightly run AND the G0.5
   market-hours window (09:30–16:00 ET) are both expressed against US/Eastern
   regardless of where the VM physically lives. Pin this with a test, not faith.
4. **Secrets stay on the VM.** Create `.env` directly on the VM (Sharadar + Alpaca
   keys). Never commit, never paste through the assistant, never echo into shell
   history or logs.
5. **Verify the data layer.** VM must reach data.nasdaq.com and the Alpaca
   endpoints, have disk headroom for the full-history SEP archive + nightly raw
   parquet, and initialize the PIT store + event log cleanly.
6. **Prove it end-to-end before trusting it.** (a) manual run → `all_ok`, PIT audit
   clean, universe = 503; then (b) a **cron-fired** throwaway run succeeds. Only
   then does the official 5-night soak start.

---

## Steps

### 0. Confirm the environment (before anything)
```bash
uname -a                      # confirm Linux
python3 --version             # need >= 3.11 (see note on pyproject below)
timedatectl | grep "Time zone" # note the VM's TZ — we override per-job anyway
nproc; df -h ~; free -h        # capacity sanity
crontab -l 2>/dev/null         # see ANTS cron jobs → avoid name/time collisions
```
> **Python note (resolved):** `pyproject.toml` pins `requires-python = ">=3.11"`
> (relaxed from an incidental `>=3.14` laptop pin — already applied). The code only
> needs 3.11+ (`datetime.fromisoformat` with `Z`, `X | Y` unions), so the VM's
> Python 3.12 is fine; no edit needed before `pip install`. (Minor follow-up: the
> black/ruff/mypy `target-version`/`python_version` in pyproject still say 3.14 —
> tool targets only, not the floor; align to 3.11 when convenient.)

### 1. Isolated checkout
```bash
mkdir -p ~/axrzceFund && cd ~/axrzceFund         # NOT under the ANTS tree
git clone https://github.com/AXRZCE/axrzceFund.git .   # token auth if private
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e .                        # deps from pyproject
```

### 2. Secrets on the VM only (constraint 4)
```bash
cat > .env <<'EOF'      # fill in real values IN THIS FILE ON THE VM — do not share
NASDAQ_DATA_LINK_API_KEY=...
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
EOF
chmod 600 .env
```
`.env` is already in `.gitignore` — confirm `git status` shows it untracked.

### 3. Data-layer verification (constraint 5)
```bash
.venv/bin/python ops/verify_sharadar.py     # expect all 5 datasets OK
.venv/bin/python ops/verify_alpaca.py        # expect ACTIVE, IEX bars
```

### 4. Manual pipeline proof (constraint 6a)
```bash
.venv/bin/python ops/nightly_ingest.py
# expect: ALL OK: True, PIT audit violations: 0
.venv/bin/python -c "from data.pit_store import PITStore; from datetime import datetime,timezone; s=PITStore(); print('universe', len(s.get_universe('SP500', datetime.now(timezone.utc).isoformat())))"
# expect: universe 503
```

### 5. cron with explicit TZ (constraints 2, 3)
Append to `crontab -e` (use unique comments so ANTS jobs are never touched):
```cron
CRON_TZ=America/New_York
# axrzceFund nightly soak — 21:30 ET (after Sharadar EOD)
30 21 * * *  cd $HOME/axrzceFund && .venv/bin/python ops/nightly_ingest.py >> var/ingestion_logs/cron_soak.log 2>&1
# axrzceFund G0.5 broker round-trip — one-shot, 10:00 ET market hours (remove after it passes)
0 10 16 6 *  cd $HOME/axrzceFund && .venv/bin/python ops/broker_roundtrip.py >> var/g05/cron_g05.log 2>&1
```
> If this cron build ignores `CRON_TZ`, use a systemd timer with
> `OnCalendar=*-*-* 21:30:00 America/New_York` instead — more robust. Decide on the VM.

### 6. Cron-fired proof (constraint 6b — THE gate to starting the clock)
Temporarily add a throwaway line firing ~3 min out, watch it fire, confirm it
wrote a `var/ingestion_logs/night_*.json` and a fresh archive, then remove it:
```cron
*/1 * * * *  cd $HOME/axrzceFund && .venv/bin/python ops/nightly_ingest.py >> var/ingestion_logs/cron_test.log 2>&1
```
**Only after a cron-fired run produces a clean night summary does the official soak begin.**

### 7. Decommission the laptop (once the VM cron run is proven)
On the laptop, disable the now-redundant tasks so there's one canonical soak host:
```
schtasks /change /tn "axrzceFund nightly ingestion" /disable
schtasks /change /tn "axrzceFund G0.5 broker roundtrip (one-shot)" /disable
```
And revert the laptop power hacks: `powercfg /change standby-timeout-ac 30`.

---

## Soak counting (unchanged rules)
5 consecutive clean cron-fired nights, zero unexplained row-count deviations.
A missed night restarts the count. G0.4 replay re-confirmed against one VM
soak-night archive. G0.5 green from the VM cron one-shot. Then the signed memo.
