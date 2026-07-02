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
