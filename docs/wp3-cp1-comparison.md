# WP3 CP1b — BULL-seat comparison: results + verdict

**Run of record: RUN3** — `results/wp3_cp1/run3/{comparison.json, replay_stamps.jsonl}`.
Bar authority: [wp3-cp1-rubric.md](wp3-cp1-rubric.md) §5 (frozen at CP1a, applied **unchanged** across
all runs). Run1 (discarded) and run2 (diagnostic, INCONCLUSIVE) are retained as history in §H below.

## ✅ VERDICT (run3): SEAT THE CHINESE CANDIDATE — **GLM-5.2** (`z-ai/glm-5.2`)

A fully valid run: all 3 models completed 16/16 cells (schema 1.0, zero transport failures, zero
truncations), the Western baseline is **valid** (mean 0.7188, status OK), and every cell was judged
under **rubric conditions** — all 3 memos masked together, order randomized on the deterministic
per-cell seed (`n_judged_together=3` in all 16 cells; run2's solo-judging defect is gone).

| Gate (frozen at CP1a) | GLM-5.2 | DeepSeek V4-Pro |
|---|---|---|
| G1 `schema_valid_rate ≥ 0.90` | 1.00 ✓ | 1.00 ✓ |
| G2 `mean_composite ≥ 0.70` | **0.7383 ✓** | 0.5938 ✗ |
| G3 `mean ≥ west(0.7188) − 0.05 = 0.6688` | **0.7383 ✓** | 0.5938 ✗ |
| C3 disqualified? | no | no |
| **Passes** | **YES → seated** | no (complete run, genuine fail) |

One passer → no tie-break needed. DeepSeek's fail is a **valid, complete** assessment this time (16/16
scored) — not an artifact. The Grok fallback does **not** fire (it required *both* to fail).
**Seat use is gated:** BULL-01 = GLM-5.2 takes effect only after reviewer verification of this artifact
and Akshar's clearance; no CP2 work (debate code, seat wiring) before that.

---

## Contract items 1–8 (run3)

### 1. C3 memorization probe — PASS (committed earlier, not re-run)
0/16 hit-rate for all three models (±1% tolerance, 0.25 disqualification threshold) → none memorized the
golden window; none disqualified. Spend $0.011. (`results/wp3_cp1/c3_probe.json`.)

### 2. Per-model results (16 cells × 3 models = 48 memos, all scored)

| Model | status | n_scored | mean_composite | schema_valid_rate | grounding_mean (D1) | cost | tokens (p/c) | calls |
|---|---|---|---|---|---|---|---|---|
| **GLM-5.2** | OK | 16/16 | **0.7383** | 1.00 | 2.38 | $0.0936 | 18496 / 15744 | 16 |
| gemini-3.1-pro (baseline) | OK | 16/16 | 0.7188 | 1.00 | 2.94 | $0.5931 | 23176 / 45562 | 16 |
| DeepSeek V4-Pro | OK | 16/16 | 0.5938 | 1.00 | 2.06 | $0.2437 | 21907 / 61173 | 19 |

**Failed/retried cells:** none failed. DeepSeek used the one P2 retry in 3 cells (19 calls for 16
memos), all resolving schema-valid — pacing (5s) + longer backoff fixed run2's transport failures
(0 this run; `fail_reasons` = `ok:16` for all three). No truncations (`max_tokens=4096` +
`finish_reason=length` handling).

**Per-cell scores (auditable — the means are computed from these):** D1,D2,D3,D4 (composite)

| cell | GLM-5.2 | WEST baseline | DeepSeek |
|---|---|---|---|
| 0623/AVGO | 1,4,4,4 (0.8125) | 4,3,3,3 (0.8125) | 2,2,3,2 (0.5625) |
| 0623/COST | 3,3,4,4 (0.8750) | 4,3,4,3 (0.8750) | 1,2,3,3 (0.5625) |
| 0623/MDT | 4,3,4,3 (0.8750) | 4,3,4,3 (0.8750) | 2,2,3,3 (0.6250) |
| 0623/LULU | 1,1,2,2 (0.3750) | 0,1,3,3 (0.4375) | 2,2,2,2 (0.5000) |
| 0624/AVGO | 2,3,4,4 (0.8125) | 4,3,4,3 (0.8750) | 4,3,4,3 (0.8750) |
| 0624/COST | 3,3,3,3 (0.7500) | 4,3,4,3 (0.8750) | 2,2,2,2 (0.5000) |
| 0624/MDT | 2,3,3,4 (0.7500) | 2,2,3,3 (0.6250) | 4,3,3,3 (0.8125) |
| 0624/LULU | 2,2,3,3 (0.6250) | 1,1,2,3 (0.4375) | 1,1,2,2 (0.3750) |
| 0625/AVGO | 2,3,3,4 (0.7500) | 4,3,4,3 (0.8750) | 2,2,3,3 (0.6250) |
| 0625/COST | 2,3,3,4 (0.7500) | 4,3,4,3 (0.8750) | 1,2,3,3 (0.5625) |
| 0625/MDT | 4,3,4,3 (0.8750) | 2,2,3,2 (0.5625) | 3,3,3,3 (0.7500) |
| 0625/LULU | 2,2,3,3 (0.6250) | 1,1,2,3 (0.4375) | 1,1,2,3 (0.4375) |
| 0626/AVGO | 2,3,4,4 (0.8125) | 4,2,3,2 (0.6875) | 2,2,3,3 (0.6250) |
| 0626/COST | 2,2,3,3 (0.6250) | 4,3,4,4 (0.9375) | 2,2,2,2 (0.5000) |
| 0626/MDT | 2,2,3,3 (0.6250) | 3,2,3,3 (0.6875) | 2,3,3,2 (0.6250) |
| 0626/LULU | 4,3,4,3 (0.8750) | 2,2,3,3 (0.6250) | 2,2,3,2 (0.5625) |
| **mean** | **0.7383** | **0.7188** | **0.5938** |

*Reading note (honest):* GLM wins on composite (thesis coherence D3 / specificity D4) while the West
baseline has the best **grounding** (D1 2.94 vs 2.38) — visible per-cell (e.g. 0623/AVGO: GLM D1=1 vs
West D1=4). The bar weights the four dimensions equally as declared; recorded so the seat decision's
texture is auditable, not smoothed over.

### 3. Fixture hash verification (R1 integrity)
4/4 golden-day fixtures' `content_hash` matched their committed locks at use time
(`wp3_cp1_20260623..26` → all True); each re-passed the R1 date-gate vs the confirmed binding cutoff
(2026-06-16), `manifest_version=4f34593c18b7` logged per gate-pass.

### 4. Bar applied unchanged — gate-by-gate
See the verdict table above. §5 thresholds byte-identical to CP1a (G1 0.90 / G2 0.70 / G3 west−0.05);
`west_baseline_status=OK`, `west_baseline_mean=0.7188`. Outcome `SEAT_CHINESE`, seat `BULL-01-CAND-GLM`
(`z-ai/glm-5.2`), no caveat.

### 5 & 7. Spend — cumulative, honest (vs $15 cap / $12 degrade on the cumulative figure)

| Phase | USD | note |
|---|---|---|
| C3 probe | $0.011 | committed pass |
| run1 (DISCARDED) | ~$0.40 est. | uninstrumented; killed for the repo-root memo-path bug + missing instrumentation |
| run2 (diagnostic) | $0.9405 | INCONCLUSIVE — West truncated (harness bug), DeepSeek transport-failed, GLM solo-judged |
| **run3 (RECORD)** | **$1.1673** | per-model: GLM $0.0936, West $0.5931, DeepSeek $0.2437, judge $0.2369 |
| **CUMULATIVE** | **$2.5193** | never approached the $12 degrade (checked per cell) or the $15 cap |

**Triple-exposure note (auditability):** the three models saw the cell prompts a **third** time (run1
partial + run2 + run3). No validity impact — the post-cutoff date-gate is the primary anti-memorization
guard and C3 passed; every recorded score comes from run3's complete grid under deterministic-seeded
judging. Recorded for audit, not hidden.

### 6. Replay evidence
`results/wp3_cp1/run3/replay_stamps.jsonl` — **67 stamps** (48 memos + 16 judge calls + 3 DeepSeek P2
retries), **all** carrying `manifest_version=4f34593c18b7`, `config_version=4190e44258ba`,
`code_version=8bb03f3`, per-call `model_version`, `decision_ts`, and usage (tokens + USD).

### 8. Guard gap (closed at the prior checkpoint, exercised here)
Run3 memos were written only via `core/agent_output.safe_agent_output_dir` → gitignored
`var/cp1_memos/run3/` (test-enforced; gut-demo red). `.gitignore` backstop in place. Item 8c (doc_id
content scan) remains flagged for Akshar, not built.

---

## §H — History (prior runs, same frozen bar)

- **Run1 (discarded, ~$0.40):** killed mid-run — a `Path("")`-is-truthy bug wrote 23 licensed-figure
  memos into the repo working tree (cleaned before any commit/push; never entered git history) and the
  run lacked per-model/replay instrumentation. Led to the item-8 structural guard.
- **Run2 (diagnostic, $0.9405): INCONCLUSIVE, no seat.** West baseline invalid (16/16 memos truncated at
  `max_tokens=1600` — harness bug), DeepSeek INCOMPLETE (15/16 transport failures), and the reviewer
  found GLM had been judged **solo** (no 3-memo masking) — non-rubric conditions, so its 0.7227 was not
  carried into any record. Fixes: `max_tokens` 4096 + truncation handling; DeepSeek pacing/backoff;
  verdict logic hardened (invalid baseline ⇒ INCONCLUSIVE, never a hollow seat). Top-level
  `results/wp3_cp1/{comparison.json, replay_stamps.jsonl}` are run2's diagnostic artifacts.

## Next (gated)
Reviewer verifies this artifact + the seat verdict; Akshar clears the seat. Only then does CP2 begin:
BULL-01 manifest role = `z-ai/glm-5.2` (together, Western host), debate wiring per
[wp3-done-criteria.md](wp3-done-criteria.md) R2/R3. No Grok role (fallback did not fire).
