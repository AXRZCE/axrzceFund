# WP3 CP1 — Chinese open-weight BULL-seat validation: rubric + PRE-DECLARED bar

**Committed BEFORE any spend (CP1a).** This file fixes the comparison, the scoring rubric, the
family-disjoint judge, and the **numeric pass bar** *before* a single memo is generated, so the seat
decision cannot be reverse-engineered from results (R1, anti-hoax). CP1b runs the comparison and
applies this bar **as-is** — no post-hoc adjustment.

**Authority:** `docs/wp3-done-criteria.md` R1 (open-weight seat is evidence-gated), `configuration.md`
§3 (T2_A Chinese family, T3 judge ≠ judged), `backtesting-framework.md` §6 (C1 post-cutoff / C3
memorization probe). **Branch:** `phase1/wp3-debate`.

---

## 1. Compared models (added to `deploy/model_manifest.yaml`, Western-host-pinned)

| Role (manifest) | Model | Family | Host (Western, R1) | `cutoff` (availability) |
|---|---|---|---|---|
| `BULL-01-CAND-DEEPSEEK` | `deepseek/deepseek-v4-pro` | chinese | fireworks | **2026-04-30 — PROVISIONAL** |
| `BULL-01-CAND-GLM` | `z-ai/glm-5.2` | chinese | together | **2026-05-15 — PROVISIONAL** |
| `BULL-01-BASELINE-WEST` | `google/gemini-3.1-pro-preview` | google | google-vertex | 2026-02-19 (= FUND-TECH) |
| `VERIF-CP1-JUDGE` | `openai/gpt-5.4` | openai | openai | 2026-03-05 |

- **Binding cutoff (comparison) = MAX = `2026-05-15`** (`core/manifest.binding_cutoff`). Every golden day
  below is strictly after it (R1).
- **Western-host pin enforced in code:** a Chinese-origin (`family: chinese`) model pinned to a
  non-Western host **fails to load** (`core/manifest.WESTERN_HOSTS`, fail-closed; red test
  `tests/test_manifest.py::test_western_host_pin_red_a_chinese_model_on_a_non_western_host_fails`).
- ⚠️ **PROVISIONAL availability dates.** The two Chinese `cutoff` values are placeholders. **Before CP1b
  spend they MUST be confirmed against the live OpenRouter `created` field** (a spend-free metadata GET).
  If a confirmed date is later than a golden day (all are 2026-06-23…26), that day is invalid and its
  fixture is re-recorded; the R1 date-gate (`load_fixture`) re-checks at load, so a wrong date fails
  closed rather than leaking. The ~5–6-week margin (2026-05-15 → 2026-06-23) gives headroom.

## 2. Golden-day fixtures (committed hash-locks; licensed data gitignored)

Four golden days × four liquid S&P 500 tickers across four GICS sectors. Fixtures recorded spend-free
from the canonical pit_store by `ops/record_cp1_fixtures.py`; only the locks are committed.

| Fixture / lock | `decision_ts` | content_hash | tickers (sectors) |
|---|---|---|---|
| `wp3_cp1_20260623` | 2026-06-23T20:00:00Z | `bfe27ff241c51ad7` | AVGO, COST, LULU, MDT |
| `wp3_cp1_20260624` | 2026-06-24T20:00:00Z | `3b3696994b92df85` | AVGO, COST, LULU, MDT |
| `wp3_cp1_20260625` | 2026-06-25T20:00:00Z | `047b88c04c578d18` | AVGO, COST, LULU, MDT |
| `wp3_cp1_20260626` | 2026-06-26T20:00:00Z | `3639eb701dd1beb8` | AVGO, COST, LULU, MDT |

Sectors: **AVGO** (Info Tech / semis), **COST** (Consumer Staples), **LULU** (Consumer Discretionary),
**MDT** (Health Care). Each fixture carries ~17–25 trailing daily bars/ticker + the 6 ARQ fundamental
indicators (`ASSETS, EPS, EQUITY, FCF, NETINC, REVENUE`) as-of the boundary.
- *Coverage note (surfaced):* the local pit_store's deep-price set and deep-fundamentals set are
  disjoint, so these liquid names carry ~1 month of bars (not 252). Fundamentals depth is full. This is
  adequate for a **fundamental** bull thesis with recent price context; it is a data-layer limitation to
  note, not a rubric compromise. The four days sit close together (coverage window) — sector diversity
  across the four tickers is the primary source of variation.

## 3. Grid & task

- **Grid = 4 golden days × 4 tickers = 16 (day, candidate) cells.** Each of the 3 compared models
  produces one **bull-style memo/argument** per cell ⇒ **48 memos**.
- **Task per cell (identical for all models):** given ONLY the fixture's frozen data for that candidate
  (via `pit_store`, post-cutoff), construct the strongest honest **bull** case as a schema-valid
  `ResearchMemo` (§2.1) — stance/conviction, a falsifiable thesis, 3–7 cited `key_claims`, invalidation
  conditions, `what_would_change_my_mind`. Every factual claim cites a fixture `doc_id`; uncited `fact`
  claims are stripped by VERIF-01 (P2 step 3). Metered client, replay-stamped (incl. `manifest_version`).

## 4. Scoring (family-disjoint judge, masked + randomized)

- **Judge = `VERIF-CP1-JUDGE` (`openai/gpt-5.4`, family openai)** — DISJOINT from every judged family
  (google baseline, chinese ×2), enforced by `core.heterogeneity.assert_judge_disjoint`
  (`tests/test_manifest.py::test_cp1_judge_family_disjoint_from_every_compared_model`).
- **Per cell**, the judge scores all 3 memos in one call with **model identity masked** and
  **presentation order randomized** (VERIF-01 §6.5 anti-bias). The randomization seed is derived
  deterministically from the cell id (`fixture_id + ticker`) so scoring is replay-stable.
- **Schema gate (pass/fail, before scoring):** the memo must be schema-valid (§2.1 + VERIF-01 strip,
  ≤ `max_stripped_claims_pct = 30%`). One retry allowed (P2). A memo failing schema after retry scores
  **0** for that cell and counts against the model's schema-valid rate.
- **Rubric — each dimension 0–4, applied uniformly:**
  1. **Grounding / citation fidelity** — every claim cites a fixture `doc_id`; uses the fixture's actual
     figures; no uncited or fabricated numbers.
  2. **Financial-reasoning quality** — valuation logic, earnings/balance-sheet reading, catalyst
     identification: coherent and correct given the data.
  3. **Thesis coherence & falsifiability** — a clear bull thesis with explicit invalidation conditions /
     `what_would_change_my_mind`.
  4. **Argument specificity & non-triviality** — engages this company's actual situation with specific
     evidence and addresses ≥1 real risk (a bull that ignores risk is weak), not generic boilerplate.
- **Composite per memo** = (D1+D2+D3+D4) / 16 ∈ [0, 1]. **Model score** = mean composite over its 16
  cells (schema-failed cells = 0). Also recorded per model: `schema_valid_rate`, `grounding_mean` (D1),
  `cost_usd`.

## 5. PRE-DECLARED PASS BAR (frozen — CP1b applies it unchanged)

A Chinese candidate takes the **BULL-01 seat** iff it clears **all three** gates:

- **G1 — reliability:** `schema_valid_rate ≥ 0.90` (a debater that can't reliably emit valid memos is
  unusable).
- **G2 — absolute quality floor:** `mean_composite ≥ 0.70`.
- **G3 — parity with the Western frontier:** `mean_composite ≥ mean_composite(BASELINE-WEST) − 0.05`
  (the open-weight seat is only worth taking if it is not materially worse on financial reasoning).

**Selection & tie-break:**
- Both Chinese candidates clear G1–G3 → seat the higher `mean_composite`. Ties (|Δ| ≤ 0.02) break by
  (i) higher `schema_valid_rate`, then (ii) higher `grounding_mean`, then (iii) lower `cost_usd`.
- Exactly one clears → seat it.
- **Neither clears → the BULL seat FALLS BACK to `BULL-01-BASELINE-WEST`** (recorded as the verdict,
  never silent).

**C3 memorization probe (secondary backstop, build-if-cheap):** before scoring, elicit
closing-price/headline recall for the golden window from each model; a hit-rate above a pre-set
threshold disqualifies that model for that window (R1 date-gate is the primary guard; C3 is the tripwire
for a model that memorized the window anyway).

## 6. Cost plan vs the $15 cap

- ~48 bull memos + 16 judge calls (1/cell) + ≤6 C3 probes ≈ **70 calls**. Chinese open-weight on a
  Western host is cheap; the Google baseline + OpenAI judge dominate. **Expected ≈ $4–9.**
- **Hard cap = $15.** Degrade rule: if running spend reaches **$12**, stop launching new cells and
  finalize on the cells completed (report the reduced N and which cells ran) — **never exceed $15**.
- Per-model token/USD is recorded and reported at CP1b (feeds the G1.2d `≤ $8 p90 per decision` bar).

## 7. Structural open item — the fallback is NOT free (decision for Akshar, contingent on the verdict)

The 3-family decorrelation (config §3: Google / OpenAI / Chinese) **requires the Chinese family for one
debate seat.** If the Chinese BULL seat falls back to a Western frontier, BULL/BEAR/PM can no longer be
three distinct families with only two Western families available: a Western BULL collides with either
BEAR (OpenAI) or PM/MOD (Google), violating `family(BULL) ≠ family(BEAR)` or
`family(PM) ∉ {family(BULL), family(BEAR)}` (Frozen-Set §9.4). So a **fallback verdict degrades
decorrelation to two families, or requires re-introducing a 4th family** (e.g. the ADR-2-dropped
Anthropic as the optional 4th). Flagged now; resolved only if CP1b returns a fallback.

## 8. Anti-hoax commitments

- The bar (§5) is **committed before results** and applied **unchanged**; no threshold is moved to fit an
  outcome. The verdict is recorded either way (pass → seat; fail → Western fallback).
- Golden-day inputs are **frozen and hash-locked** (§2); CP1b verifies the same `content_hash`.
- The judge is **family-disjoint, masked, order-randomized**; scoring is replay-stable.
- Every memo/judge call is **metered and replay-stamped** (incl. `manifest_version`); spend is reported
  vs the cap.
- Fixtures (licensed data) are **never committed** — only the locks.
