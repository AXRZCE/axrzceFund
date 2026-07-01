# WP3 CP1b — BULL-seat comparison: results + verdict

**Run of record:** `results/wp3_cp1/comparison.json` (+ `replay_stamps.jsonl`, `c3_probe.json`).
Bar authority: [wp3-cp1-rubric.md](wp3-cp1-rubric.md) §5 (frozen at CP1a, applied **unchanged**).

## ⚠️ VERDICT: INCONCLUSIVE — no seat awarded (do NOT seat any model)

The run did **not** produce a valid seat decision. Only one of three models (GLM-5.2) yielded scorable
memos; the **Western baseline was invalid** (all memos truncated by a harness `max_tokens` bug) and
**DeepSeek was incomplete** (15/16 transport failures). With no valid baseline the **G3 parity gate
cannot be evaluated**, so the §5 bar cannot be applied — seating GLM here would be a hollow sample.
**Decision required from Akshar: rerun (fixes ready) vs. verdict** (per the standing contingency rule).

---

## 1. C3 memorization probe (mandatory, ran first) — PASS

| Model | hit-rate (±1%) | threshold | disqualified? |
|---|---|---|---|
| DeepSeek V4-Pro | 0/16 = 0.000 | 0.25 | no |
| GLM-5.2 | 0/16 = 0.000 | 0.25 | no |
| gemini-3.1-pro (baseline) | 0/16 = 0.000 | 0.25 | no |

None recalled the golden-window closes → none memorized → none disqualified. **C3 spend = $0.011.**
(`results/wp3_cp1/c3_probe.json`.)

## 2. Per-model results (16 cells × 3 models = 48 memos attempted)

| Model | status | n_scored | mean_composite | schema_valid_rate | grounding_mean | transport_fails | cost | tokens (p/c) |
|---|---|---|---|---|---|---|---|---|
| GLM-5.2 | **OK** | 16/16 | **0.7227** | 1.00 | 2.81 | 0 | $0.0923 | 19661 / 15460 |
| DeepSeek V4-Pro | **INCOMPLETE_TRANSPORT** | 0/16 | — | — | — | **15** | $0.0248 | 4609 / 6400 |
| gemini-3.1-pro (baseline) | **INVALID_LOWYIELD** | 0/16 | — | 0.00 | — | 0 | $0.7004 | 46352 / 50644 |

**GLM-5.2 per-cell scores (auditable — the mean is computed from these 16):**

| cell | D1 | D2 | D3 | D4 | composite |
|---|---|---|---|---|---|
| 0623/AVGO | 3 | 3 | 4 | 3 | 0.8125 |
| 0623/COST | 2 | 2 | 3 | 3 | 0.6250 |
| 0623/MDT | 4 | 3 | 4 | 3 | 0.8750 |
| 0623/LULU | 2 | 2 | 3 | 3 | 0.6250 |
| 0624/AVGO | 3 | 3 | 4 | 3 | 0.8125 |
| 0624/COST | 3 | 3 | 3 | 3 | 0.7500 |
| 0624/MDT | 3 | 3 | 3 | 3 | 0.7500 |
| 0624/LULU | 2 | 2 | 2 | 2 | 0.5000 |
| 0625/AVGO | 4 | 3 | 4 | 3 | 0.8750 |
| 0625/COST | 2 | 2 | 3 | 3 | 0.6250 |
| 0625/MDT | 4 | 3 | 4 | 3 | 0.8750 |
| 0625/LULU | 2 | 2 | 3 | 2 | 0.5625 |
| 0626/AVGO | 3 | 3 | 4 | 3 | 0.8125 |
| 0626/COST | 3 | 2 | 3 | 3 | 0.6875 |
| 0626/MDT | 3 | 3 | 3 | 3 | 0.7500 |
| 0626/LULU | 2 | 2 | 3 | 3 | 0.6250 |
| **mean** | | | | | **0.7227** |

**Failed / incomplete cells (which, why, resolution):**
- **DeepSeek — 15/16 cells: transport/serving `LLMError`** (fail-closed after the client's bounded
  retries). It succeeded in the single C3 call, so the failures are consistent with **rate-limiting on
  rapid Fireworks calls**, not a bad pin. Only 4 metered calls landed. *(Exact error text not captured —
  run2's stderr was discarded; the rerun captures it.)* → INCOMPLETE, **not scored on a hollow sample**
  (contingency rule); the bar was **not** lowered or re-weighted to compensate.
- **gemini-3.1-pro — 16/16 cells: memo JSON truncated** at `max_tokens=1600` (each call emitted
  ~1580 completion tokens then cut off → unparseable JSON → 0 valid memos, all files `{}`). **This is a
  harness bug, not a model deficiency.** Fixed (see §"Harness fixes").
- **GLM-5.2 — 0 failures**, 16/16 schema-valid on first attempt.

## 3. Fixture hash verification (R1 integrity)

All four golden-day fixtures' `content_hash` matched their committed locks at use time:
`wp3_cp1_20260623..26` → True, True, True, True. Each also re-passed the R1 date-gate against the
confirmed binding cutoff (2026-06-16).

## 4. §5 bar applied — gate-by-gate

The bar is byte-identical to CP1a (`G1 schema≥0.90, G2 mean≥0.70, G3 mean≥west_baseline−0.05`).
**It could not be validly applied**: `west_baseline_status = INVALID_LOWYIELD` (n_scored 0/16), so
`west_baseline_mean` is undefined and **G3 has no baseline**. Awarding a seat on `west=0.0` (which makes
G3 trivially true) is exactly the hollow-sample failure the rule forbids. Therefore:
- **DeepSeek:** INCOMPLETE — not evaluated.
- **GLM-5.2:** would clear G1 (1.00≥0.90) and G2 (0.7227≥0.70, thin), but **G3 is unevaluable** (no
  valid baseline). **Not seated.**
- **Verdict: INCONCLUSIVE. Seat: none.** (Grok fallback is NOT triggered — it fires only when both
  Chinese candidates are *complete* and fail; here the run itself is invalid.)

## 5 & 7. Spend actuals — cumulative, honest (vs $15 cap / $12 degrade)

| Phase | USD | note |
|---|---|---|
| C3 probe | $0.011 | instrumented |
| **run1 (DISCARDED)** | **~$0.40 (estimated)** | uninstrumented; killed after ~23 memos. Discarded for **two** reasons: the `Path("")` repo-root memo-path bug **and** missing per-model/replay instrumentation. Same `max_tokens=1600` → West truncation present here too. No exact figure (no per-call metering); estimated from run2's per-call costs. |
| run2 (of record) | $0.9405 | instrumented; per-model above. West's $0.70 was **wasted on 32 truncated calls** (the bug). |
| **CUMULATIVE** | **~$1.35** | well under the $12 degrade stop and $15 cap. |

The $12 degrade rule was checked against the **cumulative** figure each cell; it never tripped.
**Double-exposure note (auditability):** the 3 models saw the cell prompts twice (run1 partial + run2).
No validity impact — **every reported score is from run2's complete grid**, and the judge ordering is
deterministic-seeded; run1 contributed **no** scores (discarded).

## 6. Replay evidence

`results/wp3_cp1/replay_stamps.jsonl` — **69 stamps**, one per memo + judge call; **all carry
`manifest_version` = `4f34593c18b7`** (+ `model_version`, `config_version=4190e44258ba`,
`code_version=530744c`, `decision_ts`, per-call `usage`). Example:
`{"agent_id":"BULL-01-CAND-GLM","model_version":"z-ai/glm-5.2-20260616","manifest_version":"4f34593c18b7",
"decision_ts":"2026-06-23T20:00:00+00:00","usage":{"prompt_tokens":1165,"completion_tokens":896,"cost_usd":0.00535}}`.

## 8. Guard gap closed (the run1 near-miss)

Structural fix so a licensed-figure file can never again reach the tracked tree by a path bug:
- **8a:** `core/agent_output.safe_agent_output_dir` fail-closes on empty/cwd/tracked-not-gitignored
  paths (kills the `Path("")`-is-truthy class); committed test `tests/test_agent_output.py` (gut-demo
  confirmed red). The harness now resolves memos through it → gitignored `var/cp1_memos`.
- **8b:** `.gitignore` backstop (`/*BULL-0*.json`, `var/cp1_memos/`).
- **8c (flagged, not built):** a deeper guard that scans JSONs for fixture `doc_id` patterns outside
  approved dirs — WP4-adjacent; awaiting Akshar's go.

---

## Root cause & harness fixes (applied — rerun-ready)

1. **West truncation (my bug):** `max_tokens` 1600 → **4096**, and `_bull_memo` now treats
   `finish_reason == "length"` as a truncation (retry, then record `reason="truncated"`) rather than a
   silent schema fail.
2. **Verdict integrity (logic bug):** `_aggregate_and_verdict` now assigns a per-model `status`
   (`OK` / `INCOMPLETE_TRANSPORT` / `INVALID_LOWYIELD`) and returns **INCONCLUSIVE** whenever the
   baseline is not `OK` — a seat can never rest on an invalid baseline again (this is why the artifact
   above reads INCONCLUSIVE, not "SEAT GLM").
3. **DeepSeek transport (to address on rerun):** capture stderr; add pacing / longer backoff for the
   Fireworks-hosted DeepSeek calls (rate-limit hypothesis); confirm the exact error.

## Recommendation — Akshar's call (rerun vs. verdict)

**Recommend a rerun** with the fixes above (est. ~$1 more; cumulative would be ~$2.3, still << $15). A
rerun gives a **valid** Western baseline + a complete DeepSeek, so the §5 bar can actually be applied.
The alternative — accept a partial verdict — is not sound here because the baseline (the yardstick) was
never measured. **No CP2 work (no debate, no seat wiring, no Grok role) proceeds until a valid CP1b
verdict is verified and the seat is cleared.**
