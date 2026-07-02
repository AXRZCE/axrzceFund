# WP3 readout — Debate + ballot + PM + judge + shadow-ensemble (R1–R7)

**Branch:** `phase1/wp3-debate` → PR to `main` (Akshar's merge gate). **Done-criteria:**
[wp3-done-criteria.md](wp3-done-criteria.md) (committed before code, `a3b3529`), all seven rulings
closed with committed artifacts. Per-checkpoint detail: [CP1 comparison](wp3-cp1-comparison.md) ·
[CP2 readout](wp3-cp2-readout.md) · [CP3 readout](wp3-cp3-readout.md) · CP4 artifact
`results/wp3_cp4/full_smoke.json`.

## The roster, as seated (with the evidence trail)

| Seat | Model | Family / host | How it earned the seat |
|---|---|---|---|
| **BULL-01** | `z-ai/glm-5.2` | chinese / together (Western pin) | **R1 evidence-gated**: run3 of record (`results/wp3_cp1/run3/`) — mean 0.7383 vs valid West baseline 0.7188; G1/G2/G3 cleared as frozen at CP1a; reviewer recomputed; Akshar cleared. Grok fallback pre-committed, never fired. |
| BEAR-01 | `openai/gpt-5.4` | openai | ADR-2 T2_B |
| MOD-01 / PM-01 | `google/gemini-3.1-pro-preview` | google / vertex | ADR-2 T2_C (referee/synthesizer outside both debating families) |
| VERIF-01 judge seats | one per family (T3) | resolved at call time | R6: judge family ≠ judged, call-site-enforced |
| Shadows | DeepSeek V4-Pro + gemini-3.1-pro | validation scope | R7 evidence path; runtime seating fail-closed |

Frozen-Set §9.4 heterogeneity holds in CODE: `family(BULL) ≠ family(BEAR)`, PM/MOD outside both,
judge ≠ judged — via `core/heterogeneity.py` (CP0), red-tested at every consumer.

## R1–R7 — proof + anti-hoax confirmation (every gut demonstrated red, then restored)

| R | Proof | Gut → red demonstration |
|---|---|---|
| R1 open-weight seat evidence-gated | run3 comparison committed; Western-host pin fail-closed; bar frozen BEFORE results (CP1a) and applied unchanged; run2's invalid run correctly INCONCLUSIVE (no hollow seat) | non-Western host → `DID NOT RAISE` when gutted |
| R2 genuine divergence | debate machinery code-enforces isolation/grounding/round-cap/capitulation; MOD neutrality schema-enforced; transcripts show the bear attacking by reference (57× FCF, DCF-floor circularity) | capitulation checks disabled → sycophantic-bear tests red |
| R3 computed ballot | P5 tally from sealed votes; `deep_loop.py:135` hardcode deleted; margin denominator RULED (R4-PRE → decision-protocols P5.3); boundary test caught a real IEEE-754 bug | WP1 hardcode resurrected → 7 tests red |
| R4 contested mechanics | ×0.5 haircut AND ≤0.5% cap, cap binding after haircut; boundary at exactly 0.20; CP4 smoke produced an ORGANIC contested ballot (margin 0.061) | haircut gut → 3 red; cap gut → 2 red (test cases separate the guts) |
| R5 PM grounded + replay | server-authoritative sizing; canned-PM/override/edge guards; `reconstruct_decision` structurally client-free; `manifest_version` first-class (CP0, un-conflated from config_version) | manifest_version dropped → identities collapse → red; heterogeneity gut → red |
| R6 judge disjoint | family resolved at CALL TIME (per-family T3 seats); masked + seed-randomized; verdicts must cite real transcript claims | call-site loop disabled → forced same-family `DID NOT RAISE` |
| R7 decorrelation measured | shadow votes LOGGED, metric computed from logs; isolation STRUCTURAL (AST-scanned no-live-state-import) | live-state import added → red; empty-log tolerance → red |

Suite: **238 passed** (WP2 close: 179). Stubs remaining in `graphs/stubs/`: research trio +
VERIF-01 pass-through + PMORT-01 + StubVoters — every role with a real implementation left the
quarantine (BULL/BEAR/MOD at CP2, PM at CP3).

## The four E2E smokes (one per unused golden day/sector — all hash-verified fixtures)

| Smoke | Day/candidate | What it proved | Notable |
|---|---|---|---|
| CP2 | 0624 / AVGO (semis) | first 3-family debate; computed ballot | bear attacked the memo's own valuation by reference |
| CP3 | 0625 / MDT (health) | PM traded WITH the ballot at 0.735% | bear-crux haircut ×0.7 fired ("size like it") |
| CP4 | 0626 / COST (staples) | full pipeline incl. judge + shadows | **organic CONTESTED ballot (margin 0.061) → PM chose no_trade**; decorrelation 0.30 measured |
| (CP1) | 0623–26 grid | the seat itself | 16 cells × 3 models, rubric conditions |

## Spend — the complete honest ledger

| Stage | Recorded | Discarded (est., counted) | Stage total | Cap |
|---|---|---|---|---|
| CP1 C3 probe | $0.011 | — | $0.011 | — |
| CP1 run1 | — | ~$0.40 (path+instrumentation bug) | ~$0.40 | $15 |
| CP1 run2 (diagnostic) | $0.9405 | — | $0.9405 | $15 |
| CP1 run3 (record) | $1.1673 | — | $1.1673 | $15 |
| CP2 smoke | $0.2127 | ~$0.60 (truncation ×2) | ~$0.81 | $3 |
| CP3 smoke | $0.2450 | — | $0.2450 | $3 |
| CP4 smoke | $0.3326 | ~$0.50 (grounding-corpus + GLM closing-only) | ~$0.83 | $3 |
| **WP3 total** | **$2.909** | **~$1.50** | **~$4.41** | (each stage under its cap) |

Every discarded attempt failed CLOSED (truncation/validation → raise, never a silent partial) and
is counted, not hidden. All 100+ replay stamps across the smokes carry `manifest_version`.

## Known limitations carried forward (flagged, not hidden)

1. **Edge-cost placeholder (WP4):** `ASSUMED_ROUND_TRIP_COST_BPS = 20` in graphs/pm.py until the
   backtesting-framework cost model lands — the edge≥3× check is real; its cost input is a
   documented stand-in.
2. **Shadow budget/sampling (WP6 open, decision for Akshar):** shadows multiply per-cycle LLM cost
   by ~the number of shadow families (~+$0.03/cycle at today's 2 shadows — small, but WP6 runs
   daily and the shadow pool may grow). Propose: shadow every cycle during the WP6 dry-run week
   (the decorrelation record is the point of the week), then sample (e.g. every 2nd–3rd cycle or a
   per-day shadow budget) from WP7. Decide at WP6 open.
3. **Decorrelation N=1:** the 0.30 agreement rate is one cycle's measurement; the metric matures
   over WP6's daily cycles.
4. **SF-5 resolution note:** with the 3-family roster the debate's judge always has exactly one
   disjoint family (google); the no-alternative fallback exists in code and is logged — it has
   never fired, and cannot while three families are seated.
5. **P3 debate-eligibility gate + P5 fresh-instance voting subtleties:** the deep loop still runs
   `debate_gate` as always-eligible and skeleton votes via StubVoters; the P3 gate logic and
   production vote-casting wiring into the loop land with WP4/WP6 integration (the real casting
   machinery — `cast_votes`, constitutional stances — exists and is smoke-proven).

## Gate

All seven rulings closed; PR opened for the reviewer's full-branch verification, then **Akshar's
WP3 merge gate**. Not self-merged. WP4 opens with its OWN committed done-criteria before any code —
risk limits set from the actual WP2–WP3 portfolio, not pre-guessed.
