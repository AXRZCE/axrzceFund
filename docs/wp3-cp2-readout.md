# WP3 CP2 — debate (R2) + ballot tally (R3): readout

**Artifact of record:** `results/wp3_cp2/debate_smoke.json` (transcript, votes, ballot, 12 replay
stamps, spend). Bar authority: [wp3-done-criteria.md](wp3-done-criteria.md) R2/R3.

## STEP 1 — Roster finalized (spend-free)

Live roles added to `deploy/model_manifest.yaml` per configuration.md §3: **BULL-01 =
`z-ai/glm-5.2`** (chinese/together — the R1 verdict seat), **BEAR-01 = `openai/gpt-5.4`**, **MOD-01 +
PM-01 = `google/gemini-3.1-pro-preview`** (vertex). All `allow_fallbacks: false`; no new slugs (all
availability dates previously confirmed). CP1 comparison roles retained as committed R1 evidence but
marked **`scope: validation`** — `Manifest.resolve_runtime()` fail-closes on them (red-tested:
`test_runtime_scope_guard_red_cand_roles_never_route_at_runtime`); the WP2 agents + all debate
machinery resolve through the runtime path. Debate binding cutoff = **2026-06-16** (GLM binds) <
first golden day 2026-06-23 ✓ (tested). Manifest edit changed `manifest_version` — by design; every
CP2 stamp carries the new hash.

## STEP 2 — Debate machinery (R2)

[graphs/debate.py](../graphs/debate.py): bull → bear → rounds ≤ `max_debate_rounds=3` (closings in
the final round) → MOD-01 neutral summary. **Code-enforced, not prompt politeness:** heterogeneity at
entry (`preflight` → `assert_distinct_debaters`, fail-closed pre-spend); isolation (context = verified
memos + opponent turns only); grounding (evidence ⊆ memo-cited doc_ids); round cap; capitulation rule
(position flip / argument echo ≥0.8 Jaccard / bear-never-attacks / closing on the wrong side ⇒
`DebateVoided`); MOD neutrality (`DebateSummary` extra=forbid — no stance field can exist; premortem
scenarios must carry observable early-warning indicators). **The WP1 debate stubs
(StubBULL01/StubBEAR01/StubMOD01) are DELETED from `graphs/stubs/`**; the deep-loop debate node takes
an injected implementation and **fails closed un-wired** (`test_unwired_debate_fails_closed`).
`CycleState.debate_summary` is now the structured §4.2 object (sanctioned by the WP1-R1 reconcile);
`ClosingStatement` added per §4.1. StubPM01 no longer casts ballots — **P5 says PM does not vote** (a
WP1 modeling error fixed); `StubVoters` casts the skeleton's deterministic mixed votes.

## STEP 3 — Ballot tally (R3)

[graphs/ballot.py](../graphs/ballot.py) `tally()`: `score(d) = Σ w·conviction·1[stance=d]` (w=1,
Phase 1–2), margin = winner-vs-runner-up gap / **total cast weight** (no_position weight included),
dissent names every actual dissenter, contested = margin < `ballot_margin_threshold` (read from
configuration.md via the new `core.config.param_number` — absent param = build error per §11).
**The `deep_loop.py:135` hardcoded BallotSummary is deleted**; the ballot node computes from the
sealed votes. Boundary pinned: margin == 0.20 exactly ⇒ NOT contested — the test **caught a real
IEEE-754 bug** (0.6−0.4 = 0.1999… < 0.20 → false contested), fixed by comparing on a rounded margin.

## STEP 4 — Red tests (all committed; two demonstrated red-on-gut, restored)

| Red test | File | Gut demo |
|---|---|---|
| Sycophantic BEAR (echo / flip) → debate voided | test_debate.py | ✅ gutted checks → `DID NOT RAISE` |
| Same-family BULL/BEAR → HeterogeneityError at preflight | test_debate.py | (primitive gut-demoed at CP0) |
| Validation-scoped BULL-01 → ManifestError at preflight | test_debate.py | — |
| 4th round → DebateRoundCapError | test_debate.py | — |
| Out-of-set doc_id → DebateGroundingError | test_debate.py | — |
| MOD stance field → ValidationError; unobservable premortem → rejected | test_debate.py | — |
| Distinct votes ⇒ distinct summary; P5 formula exact; dissenter named; boundary/tie/empty | test_ballot.py + test_deep_loop.py | ✅ resurrected WP1 hardcode → **7 tests red** |

Suite: **210 passed** (was 179 at CP1b), 7 deselected (paid integration).

## STEP 5 — E2E smoke (paid): the first three-family debate

One full cycle on hash-verified `wp3_cp1_20260624` / **AVGO**: real FUND-TECH memo → VERIF-01 →
3-round debate → MOD summary → sealed votes → computed ballot. **Genuine divergence on the record**
(transcript in the artifact): the BULL (GLM) argues cited sequential-revenue acceleration; the BEAR
(gpt-5.4) attacks **by reference** — the memo's own 57×-trailing-FCF multiple and the **circularity of
the DCF floor** ("a floor derived from aggressive growth assumptions"); MOD (gemini) mapped 6 resolved
points, 3 unresolved cruxes, a 3-scenario premortem with observable indicators (e.g. "QoQ revenue
plateaus in the next 1–2 reports"), zero stance. Votes: FUND-TECH long 0.60, BULL long 0.55
(constitutional), BEAR short 0.67 (constitutional). Tally: `weighted_score=1.15`, `margin=0.2637`,
`contested=false`, dissent = "BEAR-01 voted short (conviction 0.67)". 12 replay stamps, all carrying
the post-roster `manifest_version`. Vendor-scan clean (no licensed row data in the artifact; the memo
body stays in gitignored `var/`).

### Spend (honest ledger)

| Item | USD |
|---|---|
| Smoke attempt 1 (fail-closed: BULL round-3 truncated @2048 — fixed → 4096) | ~$0.25 est., discarded |
| Smoke attempt 2 (fail-closed: FUND-TECH vote truncated @300 — fixed → 2048 + retry) | ~$0.35 est., discarded |
| Smoke attempt 3 (of record) | **$0.2127** |
| **CP2 smoke total** | **~$0.81 est.** vs **$3 cap** |
| **Cumulative WP3 ledger** | **~$3.33** vs the caps it ran under (CP1 $15 / CP2 $3) |

Attempts 1–2 failed closed before metering could persist (the exception path); costs are estimated
from attempt-3 per-call actuals and counted, not hidden. Truncation-handling is deliberately strict —
a cut-off reply is never silently parsed.

## Next (gated — not started)

CP3 (R4 contested mechanics + R5 PM-01) begins only after reviewer verification of: stubs gone, tally
computes, red tests real, transcript divergence, spend. No PM code, no contested-haircut code yet.
