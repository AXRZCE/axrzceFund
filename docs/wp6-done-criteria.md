# WP6 — The dry-run week: done-criteria + rulings

**Committed BEFORE implementation code.** **Branch:** `phase1/wp6-dryrun` off verified merged
`origin/main` = `ae24fbc` (PR #7 — **verified by CODE CONTENT**: episodic/pmort/dashboard/wp5
artifacts present; boundary + wall tests spot-ran green. This gate caught a false "WP5 merged"
once before the real merge landed — the verification stays mandatory).
**R-numbering:** per-WP (the **WP6 R-series, R1–R10**). **Objective (plan §WP6):** the whole fund,
end-to-end, daily, on the VM, for a week — **orders logged, never submitted** — every cycle a
complete, auditable, replay-deterministic, committed record.

---

## Grounding (against fetched code)

**Track A (proven by 18+ autonomous nightly commits):** `ops/vm_git_sync.sh` (ExecStartPre —
tracked-files-only self-update, fail-open to the current checkout on network blips),
`ops/vm_commit_results.sh` (ExecStopPost — stages ONLY `results/`, vendor-guard backstop,
non-force push with rebase), `deploy/systemd/hedgefund-soak.timer` (named-TZ `America/New_York`,
`Persistent=true` catch-up). The WP6 cycle service/timer follows this exact pattern; the decision
cycle runs **post-close after the soak ingest** (soak 21:30 ET → cycle **22:15 ET**).

**Production gaps the daily entrypoint must close** (the WP3 readout's flag, enumerated —
`graphs/deep_loop.py` remains the stub skeleton; the smokes chain the real machinery ad hoc):

| Stage | Exists | Gap for a daily cycle |
|---|---|---|
| P1 candidate selection | ✗ (hardcoded in smokes) | **NEW:** the universe screen (R4) + held-position review (book names are always candidates, P1.3) |
| Daily fixture + R1 gate + lock | ✓ `record_fixture`/`load_fixture`/`write_lock` | wire per-day recording post-ingest |
| Research memos | ✓ FUND-TECH; TECH-01 exists | **R4 rules the memo set** (SENT-01 stays DEFERRED, logged — unchanged ruling) |
| VERIF-01 deterministic strip | ✓ | wire |
| Debate → judge → votes → tally | ✓ (CP2–CP4 machinery) | wire |
| PM → gate | ✓ | **NEW:** the gate needs the WEEK'S BOOK — a positions ledger accumulated from modeled fills, marked daily (feeds gate `book`, monitor positions, NAV) |
| Orders (modeled) | ✓ + THE WALL | **NEW:** per-run `wall_attested` event (R5) |
| Monitor | ✓ | **NEW:** breaker-state persistence across sessions (log-derived, like the pmort queue) |
| PMORT interim + capture | ✓ | wire (interim until horizons/stops close positions) |
| Dashboard + commit | ✓ + Track A | **NEW:** `results/wp6/cycle_<date>.json` per-cycle artifact |
| Spend cap / replay check / quote log | ✗ | **NEW:** R8 cap enforcement; R5 replay-determinism check; R2 IEX quote logging (READ-only market data — the wall blocks writes, not reads) |

---

## The three carried decisions — RULED HERE (proposals for Akshar's ratification)

### R1 — Shadow sampling (carried from WP3).
**PROPOSAL: shadow EVERY cycle during the week.** The decorrelation record is the point of the
week (the WP3 metric is N=1); at ~+$0.01–0.03/cycle for the two shadow seats it is the cheapest
data we will ever buy. The metric **accumulates daily** (pairwise stance-agreement over the week's
growing log — the artifact carries the running series, not just the day). **Per-day shadow budget
stop: $0.10** — if shadows would exceed it, they are SKIPPED for the rest of the day and the skip
is RECORDED (`shadow_skipped_budget` event) — live decisions are never affected either way
(the WP3 isolation stands). From WP7: sample every 2nd cycle (re-proposed at WP7-open with the
week's data in hand).

### R2 — Cost recalibration mechanics (the MANDATORY WP4-R6 checkpoint).
**Quote-logging the week performs (per modeled order, via the IEX feed — read-only):**
`quote_log` event with {ticker, ts, bid, ask, mid, spread_bps} captured **(a)** at decision time
(cycle run) and **(b)** at fill-model time (next-open when the modeled fill is marked). If the IEX
feed lacks a quote (entitlement/latency), the gap is RECORDED, never interpolated.
**Re-derivation at week close (a committed, re-runnable script):**
`half_spread_bps' = median(logged spread_bps)/2` across the week's quotes;
`η' = (P95(observed intraday adverse move at fill vs decision mid, bps) − 2·half_spread') / √0.02`
re-anchored at the ADV-cap boundary exactly as the WP4 derivation was (arithmetic shown in the
close-out artifact). **Ratify-don't-auto-apply:** the re-derived params are a PROPOSAL in the WP6
readout for Akshar's re-ratification (a configuration.md §6 edit in the PR) — the week itself runs
on the ratified η=50/floor=4 throughout; nothing self-applies mid-week.

### R3 — Sector/gross/net re-derivation (carried from WP4).
At week close, from the ACTUAL book the week produced: realized max single-name %, sector gross %,
total gross %, |net| % — each reported against its current limit (20%/150%/±30%) with a
recommendation per limit (keep / tighten; **loosening is out of scope** — breakers are
tighten-only by Frozen-Set §9.3 and the same conservatism is applied here). **Ratify-don't-auto-
apply**, same as R2. If the week's book is too thin to justify a change (likely at 2 candidates/
day), the honest recommendation is "keep, re-derive at WP7 close" — thin evidence is stated, not
dressed up.

---

## Operational rulings

### R4 — Universe + the implementable P1 screen (evidence-based proposal).
**Evidence:** the pit_store holds ≥6 ARQ fundamentals for **~335 liquid names** (measured at CP1a)
and `universe_membership` carries point-in-time SP500 flags; SEP price coverage is ~25–31 trailing
bars post-backfill. **PROPOSAL — the screen implementable NOW:**
`SP500 (point-in-time) ∩ fundamentals-covered ∩ ADV20 ≥ $20M ∩ price ≥ $5`, deterministically
ranked by 20-day dollar-ADV, **top 2 NEW candidates/day + all held positions** (P1.3 —
re-underwriting is mandatory). The 2/day limit is a WEEK-SCOPED operational cap (config allows 10;
first unattended week runs small — cost + attention discipline; widen at WP7-open with evidence).
**Memo set:** FUND-TECH + TECH-01 (TECH-01 gets a targeted 252-day SEP backfill for the screened
names at CP2 deploy — $0, the WP2-A1 path). **Deviation, ruled openly:** `min_memos_required = 3`
is NOT satisfiable (SENT-01 deferred — unchanged, logged ruling; MACRO/QUANT are Phase 2). The
week runs a DOCUMENTED 2-memo cycle; the P2 drop rule is waived for WP6 by this ruling and
revisited when a third memo source exists. Deferred screens recorded: event screen (no PIT news),
quant screen (no signal registry).
- **Red test:** the screen is deterministic (same store ⇒ same candidate list); a sub-floor name
  cannot enter (the gate's universe floor is the backstop); the waiver is logged per cycle.

### R5 — Clean-week definition (the exit bar).
**Target week: Mon 2026-07-06 → Fri 2026-07-10** — five consecutive NYSE trading sessions
(2026-07-03 Fri is the observed Independence Day holiday since Jul 4 is a Saturday; the target
week is holiday-free). A session COUNTS iff its cycle produced ALL of:
1. **zero live submissions** — a `wall_attested` event per run (the entrypoint self-tests
   `submit_live` raises + records zero broker-write calls);
2. **replay-determinism check passed** — decisions reconstructed from the event log equal the
   committed artifact (`reconstruct_decision` and the ballot/proposal payloads; checked in-run and
   re-checkable off-VM);
3. **all artifacts committed by the VM** (Track A: `results/wp6/cycle_<date>.json` + locks +
   dashboard refresh) — reviewable off-VM;
4. **spend within the daily cap** (R8) — actuals in the artifact;
5. **monitor ticks recorded** (breaker distances + any actions).
- **Red test:** a fabricated "clean" day missing any of the five fails the week-close audit
  script (committed, re-runnable — it recomputes the five from the artifacts, never trusts a flag).

### R6 — Missed cycle: RECORDED, never backfilled.
A session with no cycle (VM down, timer failure) yields a `cycle_missed` record (written at the
next opportunity, or reconstructed off-VM from the gap — the absence of the artifact IS the
record; the audit script derives gaps from the calendar). **PROPOSAL:** ONE missed session does
not reset the week — the week extends by one session (target +1 day, e.g. into Mon 07-13);
**2+ misses, or ANY integrity failure (a wall breach, a replay mismatch, an uncommitted artifact,
a licensed-data leak) RESETS the week.** Backfilling a missed day's cycle is forbidden — P1's
information boundary cannot be reconstructed honestly after the fact.

### R7 — Fail-closed day: a completed OBSERVATION, not a failure.
LLM outage / late data / any node exception ⇒ the run fail-closes exactly as built (`cycle_failed`
event, NO decision, no order, PMORT-pending queued where applicable) and the artifact records it.
**PROPOSAL:** such a day COUNTS toward the week (criterion: the system failed CLOSED and committed
the proof — that is precisely the operational property the week exists to demonstrate). A day that
fails OPEN (any decision/order emitted after an error) is an integrity failure ⇒ R6 reset.

### R8 — Daily spend cap, enforced in code (the WP3 degrade pattern).
**Evidence:** full cycle ≈ $0.33–0.35/candidate (CP4), PMORT ≈ $0.01, shadows ≤ $0.03 ⇒ 2
candidates + held ≈ **$0.80/day expected**. **PROPOSAL: $1.50/day HARD** (≈2× expected), enforced
in-run: degrade order = drop shadows → drop candidate #2 → fail-closed stop (never a silent
overage); **week total ≤ $10 hard.** Actuals per cycle in the artifact; cumulative in the readout.
- **Red test:** an injected cost overrun triggers the degrade chain in order, and the stop emits
  `cycle_budget_stop` with no further LLM calls that day.

### R9 — Stale / holiday / half-day.
Market-closed day (weekend/holiday) ⇒ NO cycle (the monitor's `market_open` rule; the timer fires
but the entrypoint exits with a `market_closed` record — cheap, honest, zero LLM). **Half-days**
(none in the target week; e.g. Nov 27 / Dec 24 patterns): the cycle runs at the SAME post-close
time (P1 is post-close — an early close only moves the close, not the cycle's validity); ruled now
so a future half-day is boring. Stale-data-for-held-names intraday follows the WP4 R7.3 exit-only
rule unchanged.

### R10 — The VM deploy checkpoint (WP6-CP2's gate).
The week starts ONLY after: (1) the WP6 code is merged-to-main equivalent on the branch the VM
tracks — the VM syncs `main`, so **the WP6 PR must be reviewed+merged BEFORE the week runs** (the
timer stays disabled until then); (2) **ONE supervised end-to-end cycle on the VM** (spend counted
against R8), its artifacts committed by Track A and **verified OFF-VM from git alone** (hashes,
stamps, wall attestation, replay check — the committed audit script); (3) the 252-day TECH-01
backfill + a fresh universe scan on the VM store; (4) only then does Akshar (not the agent) enable
`hedgefund-cycle.timer`. Rollback: disabling the timer is the kill switch; P12 HALT semantics
apply in-run.

---

## Build order
- **WP6-OPEN (this doc)** → STOP for Akshar's gate on R1–R10 (esp. the three carried proposals,
  the 2-memo waiver, the 2-candidate week cap, the $1.50/$10 caps, the reset rule).
- **CP1 (spend-free):** the daily entrypoint (`ops/run_daily_cycle.py`) wiring the full chain +
  universe screen + book ledger + breaker persistence + wall attestation + replay check + quote
  logging + spend governor; red tests + gut demos for every new guard; the week-close audit script.
- **CP2 (paid, ~$1):** VM deploy checkpoint per R10 — one supervised cycle, off-VM verification →
  **STOP; Akshar merges the WP6 PR and enables the timer.**
- **CP3 (the week, ≤$10):** Mon 07-06 → Fri 07-10, daily off-VM verification cadence: each
  morning, pull and run the audit script against the night's committed artifacts (≤5 min, the
  soak-ritual pattern); anomalies STOP the week per R6.
- **Close-out:** R2 recalibration + R3 re-derivation proposals from the week's logs; readout;
  checklist; the close-out PR carries the params proposals for ratification.

## Spend envelope (the whole WP)
Deploy checkpoint ≈ $0.80–1.00 · the week ≤ $10 hard (expected ≈ $4) · recalibration/close-out $0.
**WP6 cap: $12.** Cumulative fund ledger entering WP6: ≈ $4.42.

## Standing rules (unchanged)
Fixtures/licensed data never committed (locks only); vendor scan every commit; ReplayTuples with
`manifest_version` everywhere; the WALL stays until WP7's own logged, reviewed change; SENT-01
stays deferred (logged); no self-merge; every checkpoint STOPs for its gate.

**Gate (Akshar).** Ratify R1–R10 as proposed (or amend), BEFORE any implementation code. Zero
spend this checkpoint.
