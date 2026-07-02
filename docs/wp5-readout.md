# WP5 readout — PMORT-01 + learning loop (capture only) + dashboard v1 (R1–R7)

**Branch:** `phase1/wp5-learning` → PR to `main` (Akshar's merge gate). **Done-criteria:**
[wp5-done-criteria.md](wp5-done-criteria.md) (committed before code; base verified by CODE CONTENT
after the WP4 false-merge scare). **Artifacts:** `results/wp5/pmort_smoke.json` +
`results/dashboard/index.html`.

## Evidence per ruling

| R | What was built | Proof |
|---|---|---|
| **R1** family-disjoint + grounded | [graphs/pmort.py](../graphs/pmort.py): seat resolved AT CALL TIME via the REUSED CP0 primitive against the decided family; call-site assertion; citation grounding vs the decision record | forced same-family → raises (gut-demoed); canned citation → `PMORTError`; **smoke: decided=google → seat `VERIF-01-JUDGE-CHINESE` (z-ai/glm-5.2)** recorded in the artifact |
| **R2** taxonomy schema-enforced | [core/episodic.py](../core/episodic.py) `PostMortem`: §6.3 fields exactly + both guards REQUIRED (`knowable_at_decision_ts{answer, citations≥1}`; separate `process_grade`/`outcome_grade`) + non-empty `observable_that_would_have_changed` | 8 schema tests; **smoke: MDT graded process 3 / outcome 2 — "a loss that paid" is representable and was used** |
| **R3** append-only, stamped, NO weights | event-log capture (stamps incl. `manifest_version`), probation status on lesson entry, frozen models, no update/delete surface, byte-equal deterministic rebuild | **the boundary test landed FIRST** (36 fields, zero weight-like names — reviewer re-executed); rebuild recovers deliberate corruption; gut-demos red |
| **R4** retrievable, isolated | `retrieve()` by ticker/direction/tags/date; AST isolation BOTH ways (8 live modules ↛ store; store ↛ live state); §3.2 injection deferred by citation | isolation gut-demo red; distinct queries ⇒ distinct results |
| **R5** dashboard on real records | [ops/build_dashboard.py](../ops/build_dashboard.py) → `results/dashboard/index.html` (committed): seat verdict, decisions, judge/shadow, gate→orders, HALT demo, post-mortems, pending queue, spend ledger | missing artifact FAILS the build (gut-demoed red); **7 spot-values read from the artifacts at test time** (incl. cost 4.2153 bps + margin 0.061033) must appear rendered; committed-output == regeneration |
| **R6** edges | a) no_trade post-mortem captured (Phase-1-lite as ruled); b) interim ⇒ `window_days` + NO generalizable lessons (schema); c) LLMError ⇒ `pmort_pending` queued (log-derived, restart-proof), drain path | R6a ran in the smoke (COST); R6b enforced at schema level (reviewer re-executed); R6c red-tested with down-then-good client |
| **R7** the smoke | two REAL interim post-mortems on stored decisions with REAL backfilled marks | below |

Suite: **320 passed** (WP4 close: 290). Vendor scans clean.

## The smoke (real marks, real verdicts — nothing fabricated)

**Backfill ($0):** `ingest_sep(tickers=[MDT,COST,AVGO,LULU], window_days=10)` — the WP2-A1
passthrough, production path untouched. Coverage 25 bars/ticker (…06-24) → **31 bars/ticker
(…07-01), 32 rows added**. Windows recorded in the artifact; no mark interpolated.

| Record | Real outcome (4 sessions) | PMORT verdict |
|---|---|---|
| **MDT trade** (entry = the WP4 modeled fill 80.151027) | **−118.65 bps**, MAE −239.7 / MFE +103.4, stop $71.50 never breached | `unrelated_path`, **process 3 / outcome 2**, interim:true, window_days 4, no generalizable lesson (schema forbids) |
| **COST no_trade** (declined contested short) | counterfactual short **+292.59 bps** (positive = the declined short would have profited) | `unrelated_path` — an honest "we passed on a winner" record with the stored `what_would_reopen` |

Both captured through the real event-log path; the derived store rebuilt **byte-equal with the new
events**; pending queue empty after capture. Seat, stamps (`manifest_version`), and windows all in
the artifact.

**Spend:** recorded **$0.0069** (2 GLM T3 calls) + ~$0.01 discarded (attempt 1 failed closed — the
retry loop only covered parse errors, so a schema failure skipped the P2 corrective retry; fixed:
validation + grounding now retry WITH error feedback, plus a single-key envelope unwrap).
**WP5 total ≈ $0.02 vs the $2 cap. Cumulative fund ledger ≈ $4.42.**

## Gut-demo table (all red, then restored)

| Gut | Red |
|---|---|
| `weight` field added to a schema | boundary scan red |
| rebuild sort disabled | byte-equal red |
| `core.episodic` imported into `graphs/pm.py` | isolation scan red |
| call-site disjointness loop disabled | forced same-family `DID NOT RAISE` |
| dashboard loader silent-skips a missing artifact | missing-artifact test red |

## Carried to WP6 (consolidated — gate items)

1. **Cost-model recalibration (mandatory, WP4 R6):** η + half_spread from the dry-run week's
   logged IEX quotes; again at WP7 from paper fills.
2. **Sector/gross/net re-derivation** from the real book at WP6 close.
3. **Shadow-ensemble budget/sampling decision** at WP6 open.
4. **Lesson promotion + aging_review go live at WP6:** promotion to `active` needs 3 independent
   episodes (different tickers, non-overlapping months) — first arithmetically possible with WP6's
   real closed outcomes; `aging_review_days = 30` likewise. Until then everything remains
   probation/interim by construction.

## Gate

R1–R7 closed with artifact links in the done-criteria. PR opened for full-branch verification,
then **Akshar's WP5 merge gate**. Not self-merged. WP6 (dry-run week) opens with its own committed
done-criteria before any code.
