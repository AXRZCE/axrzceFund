# Incident 2026-07-02 — a VM results push carried unreviewed code to `main`

**Severity:** merge-gate bypass (process failure). **Disclosed by:** the agent, immediately and
unprompted, with a refusal to force-push a unilateral fix. **Ruling:** Akshar RATIFIED `f4fad57`
as the WP6 merge, with the conditions closed by this document and the guard below.

## What happened

During WP6-CP2 (the VM deploy checkpoint), the agent synced the VM checkout to
`phase1/wp6-dryrun` (per the checkpoint order) and then ran `ops/vm_commit_results.sh` to commit
the universe-scan artifact via Track A. The script's push target was `$AXRZCE_BRANCH` —
**defaulting to `main`** (the old line 16) — while the checkout's local `main` had been
`reset --hard` onto the branch head by `vm_git_sync.sh` (reset moves the current branch pointer;
it does not switch branches). The push therefore **fast-forwarded `origin/main` from `ae24fbc` to
`f4fad57`**: four unreviewed WP6 code commits (`23730de..5f3f3db`) plus the artifact commit —
bypassing Akshar's PR gate.

Why 18+ soak nights never hit this: the VM checkout had always been *on* `main`, so the push
target and the checkout content agreed. The branch-sync + results-push combination was the hole.

## Verified facts (reviewer-confirmed independently)

- `main@f4fad57` is **byte-identical** to the reviewer-verified `phase1/wp6-dryrun@5f3f3db` plus
  exactly one Track-A artifact commit (`results/wp6/universe_scan.json`). Nothing else rode along.
- No LLM cycle ran; no live submission occurred (the wall was never in play).
- The agent did **not** force-push a rewind: restoring `ae24fbc` would have been a unilateral
  force-push to the protected branch — the same class of action the gate forbids.

## The permanent closure (Condition A — the guard, red-tested)

`ops/vm_commit_results.sh` now enforces, in the script itself:
1. **The push target is the checkout's CURRENT branch** (`git rev-parse --abbrev-ref HEAD`;
   detached HEAD refuses) — never an env-configured other ref.
2. **A results push can never carry code:** if `origin/main..HEAD` contains any commit whose
   message is not this script's own `vm(` results prefix, the script **REFUSES (exit 1, loud
   log)** naming the foreign commits.

Red tests: `tests/test_vm_commit_guard.py` drives the real script against throwaway git repos —
the incident shape (a checkout ahead of `origin/main` with a code commit) is refused and
`origin/main` provably does not move; gut the check → the code pushes → red (demonstrated, then
restored). The tests also caught and fixed a latent staging bug (a combined `git add` with one
missing pathspec silently staged nothing).

## Ruling record

- **Ratification:** `f4fad57` stands as the WP6 code merge (content already reviewer-verified at
  CP1); the reviewer's full-branch verification proceeds against `main` as it stands.
- **R10 amendment note:** the WP6 done-criteria R10 sequence ("the WP6 PR must merge before the
  timer") is satisfied by this ratification; **everything else in R10 stands** — the timer remains
  DISABLED until the supervised cycle + off-VM audit pass and **Akshar enables it personally**.
- Linked from [wp6-readout](../wp6-readout.md) at WP6 close (Condition B).

## Addendum 2026-07-03 — the push-flakiness pattern + the self-healing hardening

**The pattern, on record:** the nightly Track-A pushes failed on TWO consecutive nights at
~01:41 UTC ("push deferred") while daytime pushes from the same VM worked — transient overnight
flakiness, cause unattributed (provider network / GitHub edge). Night `20260702`'s queued commit
was then stranded by the incident-day branch reset and recovered from the reflog (cherry-picked as
`1a5fd3c`, pushed under a hand-run guard check with explicit authorization). The nightly record on
`origin/main` is gapless again.

**The hardening (`phase1/wp6-push-selfheal`):** `vm_commit_results.sh` now (a) retries a failed
push 3× (spaced `VM_PUSH_RETRY_SLEEPS`, default 120/180s; guard re-checked before every attempt;
still non-force; the service units carry `TimeoutStopSec=900` so systemd never kills the window),
and (b) on EVERY invocation pushes already-queued `vm(` commits even when nothing new exists — the
no-op gap that stranded `20260702` is closed and red-tested.

**Standing architecture rule (Akshar, 2026-07-03):** NOTHING recurring or time-critical may depend
on a CC session — the 24/7 VM is self-sufficient for all execution and self-healing. The one-shot
origin-polling watcher used for tonight's supervised cycle is **DECOMMISSIONED after that single
run** — one-shot scaffolding only, never to be reused for recurring work. CC's recurring role
during the dry-run week is the read-only morning audit report ONLY.

## Addendum 2026-07-05 — the weekend orphaning: reset-between-invocations defeated the queued-push

**Finding (Sunday pre-week check):** all four weekend timer runs (Fri/Sat soak + cycle) executed
and recorded correctly — unit hashes matched, artifacts and events created, including the
`market_closed` records for 07-03/07-04 — but **every push attempt (12/12) failed in the nightly
01:30–02:20 UTC window while daytime writes worked** (a Sunday-daytime `push --dry-run`
authenticated and would have fast-forwarded). That is four consecutive nights of the pattern
first logged above, still unattributed because the script discarded push stderr. Worse, each
run's ExecStartPre sync (`reset --hard origin/main`) **orphaned the previous run's queued `vm(`
commit before its queued-push could deliver it** — the `night_20260702` stranding class, made
systematic (3 of 4 weekend records orphaned into the reflog; nothing lost — recovered and pushed
under Akshar's 2026-07-05 authorization). The 2026-07-03 hardening's red test modeled the no-op
gap *within* an invocation but never the sync *between* invocations.

**The closure (`phase1/wp6-sync-queuefix`):** (a) `vm_commit_results.sh` now captures and logs
push stderr — every future failure is attributable; (b) `vm_git_sync.sh` REBASES queued
`vm(`-only commits onto the new head instead of resetting them away — any foreign commit still
triggers the full reset, the 2026-07-02 protection deliberately unweakened — red-tested in the
between-invocations shape; (c) `hedgefund-flush.timer` (12:00 UTC daily) delivers any queued
results in the reliable daytime window before the 09:00 ET morning audit. Nightly-window root
cause: under investigation (candidate: provider nightly maintenance/backup window); to be
recorded here when named.
