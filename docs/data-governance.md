# data-governance.md — Vendor data, fixtures, and the public repo

**Status:** v1.0 standing policy (regime shipped in WP2; on `main`).
**Applies to:** the entire repo — which is **PUBLIC**. This doc is the authority on what may and may
not enter git.
**See also:** [api-data-sources.md](api-data-sources.md) (what the vendor data IS + PIT discipline),
[configuration.md](configuration.md) (secrets in env only), [vm-git-wiring.md](vm-git-wiring.md) (the
VM commit path + guard backstop), [wp2-readout.md](wp2-readout.md) (where the regime landed).

## 1. The one rule
Licensed vendor data and secrets **NEVER** enter the repo. The repo is public; a single leaked
fixture is a licensing breach. Our OWN outputs (reports, orders, fills, computed stats, row
counts/statuses) commit normally — they don't carry vendor row values.

Licensed sources today: **Sharadar** (SF1 fundamentals, SEP prices, ACTIONS, TICKERS, SP500 history)
via Nasdaq Data Link; **Alpaca IEX** bars; **Alpaca News** (Benzinga-sourced).

## 2. Fixtures: gitignored, hash-locked
- Golden/recorded fixtures hold frozen vendor rows and are **gitignored**: `data/fixtures/recorded/`
  and `data/fixtures/golden/` (see `.gitignore`).
- What IS committed is the content-hash **LOCK** only: `data/fixtures/locks/*.lock.json`. A lock
  carries `fixture_id`, `decision_ts`, `tickers`, `source`, `recorded_at`, a `content_hash`, and a
  `payload_summary` (row **counts**, not values) — no vendor row values. Example on `main`:
  `data/fixtures/locks/tech_01_20260701.lock.json` (`content_hash 1739d52198c9eba2`).
- **Replay contract:** the harness re-records the fixture from the canonical `pit_store` with the
  locked params; the recomputed `content_hash` must match the lock. Tests **skip** when the local
  fixture is absent (they never fail for its absence, and never commit it).

## 3. The commit-guard (vendor-agnostic — path / extension / schema)
`ops/precommit_guard.py`, wired as `ops/git-hooks/pre-commit`. Blocks a commit if any staged file is
vendor data, by three rules:
- **Path:** anything under `data/fixtures/` (except `/locks/`, `*.lock.json`, and `*.py`).
- **Extension:** `.parquet`, `.duckdb` (raw vendor stores).
- **Schema:** a `.json` carrying vendor row arrays (`price_bars` / `fundamentals` / `news`) at top
  level or under `payload` — catches a leak committed OUTSIDE `data/fixtures/`. Our
  reports/orders/fills don't match this shape and pass.

Activate on every clone (and on the VM via `ops/vm_bootstrap.sh`):
```
git config core.hooksPath ops/git-hooks
```
**Honest limitation (stated in the guard itself):** this is a LOCAL hook. It only guards `git commit`
where `core.hooksPath` is set, is bypassable with `--no-verify`, and is **not** a server-side gate.
It is *a* guard for a solo public repo, not a substitute for repo-side controls. On the VM it is the
backstop against vendor data ever reaching `results/` (see vm-git-wiring.md).

## 4. History scrub + pending GC (the WP2 leak incident)
A golden fixture was once committed and leaked into history. Remediation, done:
- `git filter-repo` removed the fixture from **ALL** history.
- All branches were **force-pushed** to the scrubbed history.
- The `.gitignore` entries + the commit-guard were added so it cannot recur.

**OPEN ITEM:** a **GitHub Support garbage-collection request is PENDING** to purge the now-unreachable
blob from GitHub's storage — a force-push makes it unreachable from any ref but does not immediately
GC it server-side, and it can remain retrievable by its old SHA until GitHub GCs. This item stays
**open until GitHub confirms** the blob is gone. `ops/vm_sync_to_cleaned_history.sh` is the one-time
tool that moves a live checkout (e.g. the VM) onto a rewritten history.

## 5. Secrets
Vendor API keys live in environment variables only (`NASDAQ_DATA_LINK_API_KEY`, `APCA_API_KEY_ID`,
`APCA_API_SECRET_KEY`, plus `OPENROUTER_API_KEY`) — never in config files, prompts, logs, or the
event log (see configuration.md). `.env`, `*.key`, `*.pem`, `credentials.json`, and `secrets/` are
gitignored.

## 6. What commits normally (for the avoidance of doubt)
Our derived outputs: `results/` proofs (soak-night summaries, broker drills — counts/statuses/flags,
orders/fills), agent memos, code, docs, and the fixture **locks**. These are the fund's own
artifacts, not vendor rows. The VM commits its `results/` proofs autonomously (vm-git-wiring.md); the
commit-guard is the backstop if vendor-shaped data ever reaches that path.
