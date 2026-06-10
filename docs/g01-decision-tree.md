# G0.1 Readout Decision Tree — pre-committed before the ensemble completed

**Status:** Recorded 2026-06-10, while the 20-seed gate ensemble (seeds {0..19}) was
still running and its results unknown. This document is committed to git BEFORE the
readout is read, so that the interpretation of each possible outcome is fixed a
priori. Deciding what an outcome means after seeing it is the same contamination
G0.1 exists to catch — applied one level up.

**Approved by:** User (project owner), 2026-06-10, verbatim instruction.

---

## Outcome 1 — Gate passes

(median PBO ≥ 0.60, PBO > 0.50 in ≥ 80% of seeds, median negative DSR p ≥ 0.20,
positive DSR p < 0.05 in all 20 seeds)

G0.1 is done. Lock it: commit the harness + controls + the full readout artifact,
append the numbers to the G0 memo draft, and move on. **No "one more confirmation
run"** — repeated re-running of a passed gate is its own selection bias.

## Outcome 2 — Negative control fails the PBO arm

Do **NOT** amend the threshold — that would be a post-observation amendment, which
the amendment rule forbids mid-evaluation. Treat it as a diagnosis problem with a
measurable criterion:

1. **Measure the effective number of independent trials.** Compute the correlation
   matrix of the ~208 trials' OOS return series; effective N = (Σλ)² / Σλ² over its
   eigenvalues. Expectation: far below 208 — plausibly 15–40 — because
   within-family trials are near-clones. That number *explains* PBO ≈ 0.5
   mechanically: CSCV can only detect selection bias proportional to how much
   genuine selection occurred.

2. **If effective N is low, the control is unrepresentative; redesigning it is
   legitimate — but only this way:** set the design target *a priori* (e.g.,
   effective N ≥ 60); achieve it by construction (more families, fewer trials per
   family, decorrelated feature seeds, possibly independent noise sub-panels per
   family); verify effective N hits the target *before* looking at PBO; and then
   **run the redesigned gate on fresh pre-committed seeds {20..39}, not {0..19}.**
   Seeds {0..19} become diagnosis data; reusing them for the re-gate would be
   fitting the control to the seeds. The amendment log records the redesign with
   the effective-N rationale, dated before the re-run.

3. **If effective N is already high and PBO still sits near 0.5:** stop and send
   the user everything. That would be a genuine finding about CSCV's power at this
   trial structure, and the response (possibly redesigning the gate statistic)
   is a joint decision, not a unilateral one.

## Outcome 3 — Positive control flickers

(any seed with DSR p ≥ 0.05)

That is a **harness bug until proven otherwise** — a true SR≈1 edge with 20 honest
evaluations should not produce false negatives. Check, in order:

1. Realized IC per failing seed (generator drift?)
2. Purge counts (over-purging shrinking the sample?)
3. DSR inputs (is the registry N correct per ensemble run — the in-memory
   per-run registry matters here)

## Standing check (any outcome)

Confirm in the readout that the **negative DSR arm is computed on the selected
(in-sample best) trial, deflated by the full registry N** — not on an average
trial. The arm only means something if it deflates the same selection PBO judges.

> Code confirmation (recorded here pre-readout): `harness/fraud_catch.py
> run_control()` computes `best_idx = argmax(trial_sharpes)`, takes `sr_hat` from
> that selected trial, and deflates with `n_trials` = full registry count from
> `registry.dsr_inputs()`. The DSR arm and the PBO arm judge the same selection.
