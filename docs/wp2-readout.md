# WP2 readout — real research agents on post-cutoff fixtures

**Status: WP2 complete.** Two research agents are proven end-to-end on post-cutoff, R1-gated
fixtures; SENT-01 is deferred by a logged ruling. All five WP2 rulings (R1–R5) hold, every anti-hoax
test bites, and total live spend is **$0.15** of the ~$15 cap.

## Agents

| Agent | Model (provider) | Status | Fixture | Live cost |
|---|---|---|---|---|
| FUND-TECH | `gemini-3.1-pro-preview` (google-vertex) | ✅ proven | `fund_tech_20260624` — BNC/SUNB/BIOX SF1 | ~$0.04 |
| TECH-01 | `gemini-2.5-flash-lite` (google-vertex) | ✅ proven | `tech_01_20260701` — NVDA/AAPL/MSFT SEP, 309 trailing days | ~$0.0004 |
| SENT-01 | `gpt-5.4` (openai) | ⏸ deferred (ruling) | — (no PIT news source) | — |

## The five rulings
- **R1 (post-cutoff gate).** `load_fixture(for_roles=[role])` rejects any `decision_ts <= binding_cutoff`.
  FUND-TECH (2026-06-24) and TECH-01 (2026-07-01) clear their binding cutoffs (2026-02-19 / 2025-07-22).
  A pre-cutoff fixture is rejected — `tests/test_fixtures_gate.py`.
- **R2 (PIT reads).** Fixtures are frozen from `pit_store` as-of `decision_ts`; `audit_lookahead()` returns
  0 offending rows on both. TECH-01's SEP backfill stamps `available_at` = ingestion time (≤ `decision_ts`),
  which is conservative (later availability = less information), not look-ahead.
- **R3 (schema + VERIF-01).** Both memos are `verify_memo`-valid with their §3 block; a constructed bad
  memo (missing/renamed block, out-of-range fields) is rejected — `tests/test_verif01.py`.
- **R4 (real metering).** Cost is read from OpenRouter's `usage.cost`; the client raises rather than record
  a guessed cost; the tests assert `usage_cost_usd > 0` **and** the logged event's cost > 0, so a canned
  literal with cost 0 goes red.
- **R5 (honest replay).** The ReplayTuple is stamped with the fixture `decision_ts` (not wall-clock), the
  real served `model_version`, and the `manifest_version` — a replay at a different boundary correctly differs.
- **Grounding.** Each memo's **fact** claims cite the fixture's own doc_ids (`sf1:` for FUND-TECH, `sep:` for
  TECH-01). Anti-hoax gut→red: a canned/fabricated memo has no real metered cost (R4 red) and cannot cite
  this fixture's specific bars (grounding red).

## TECH-01 — what was built
- **SEP backfill capability.** The store held only ~13 SEP days. A full-universe wide-window pull ends the
  response prematurely, so `ingest_sep` gained an optional `tickers` passthrough → a small, reliable
  server-side-filtered backfill (NVDA/AAPL/MSFT → **309** trailing trading days). Default (no tickers) is
  byte-identical to the production soak.
- **Agent** (`graphs/agents/tech_01.py`) mirrors `run_fund_tech`. The four §3.4 `technical_block` fields
  (trend / support-resistance levels / ADV liquidity / abnormal volume) are computed **objectively** from the
  SEP series and made **authoritative in code** (not model-trusted); the model owns the thesis / stance /
  key_claims. Live NVDA memo: stance `neutral`, trend `range`, key_levels `[86.62, 189.8, 232.28, 236.54]`,
  `abnormal_volume` False; grounded on ≥2 real bars; $0.0004.
- Golden fixture is **gitignored** (licensed SEP data); only the hash-lock
  (`data/fixtures/locks/tech_01_20260701.lock.json`, `content_hash 1739d52198c9eba2`) is committed.

## SENT-01 — deferred (logged ruling)
`docs/wp2-sent01-defer-ruling.md`. SENT-01 has no PIT-correct news path: `pit_store` has no news
table/read, and an honest news source is a **data-layer work package** outside WP2 (a news table +
`get_news`/`insert_news`, an Alpaca news adapter, a `news` branch in `record_fixture` + `audit_lookahead`,
and rewrites of two anti-hoax tests that currently forbid it) that would also be **hollow** on day one —
SENT-01's job is novelty detection, which needs a trailing coverage history that cannot exist the day the
table is created (the same "greener-than-it-is" hazard Amendment A1 refused for TECH-01). It ships
deferred, not faked; the un-defer condition is logged. `tests/integration/test_sent_01.py` is an explicit
module skip marking the deferral.

## Adversarial review (pre-readout)
A 4-verifier adversarial pass tried to refute the WP2 claims. **R1/R2/R5 hold** (verified arithmetically).
**Regressions/leak hold** — markers correct (live-call tests are `@pytest.mark.integration`, deselected by
default so no accidental spend; the pure-unit `is_metered` test always runs), golden fixtures gitignored,
only hash-locks committed, no stray writes. **SENT-01 defer holds** (refined to lead with the scope +
hollowness arguments). The **TECH-01 anti-hoax was found weakened** (the block was type-checked only and
model-trusted; grounding passed on a single guessable date) and was **hardened** (`0579249`): the block is
now authoritative in code and asserted equal to the fixture-recomputed values, and grounding requires
fact-claim citations of ≥2 real bars with no invented dates.

## Spend
**$0.15** total of the $20 OpenRouter credit (~$15 WP2 cap). FUND-TECH ~$0.04; TECH-01 live calls ~$0.001;
the balance is prior client-metering probes.

## Commit trail (`phase1/wp2-agents`)
VERIF-01 `0d6d5ea` → metered client `6aef5a2` → FUND-TECH `08185c7` → leak-fix `0c6eb8f`/`749daa3`/`55015ac`
→ plan amend `17a1f07` → TECH-01 `10ade17` → SENT-01 defer `33b2513` → anti-hoax hardening `0579249`.
(The vendor-data history scrub + VM git wiring landed on `main` separately; see `docs/vm-git-wiring.md`.)

## Follow-ups (out of WP2 scope)
- **SENT-01 un-defer:** a forward-only PIT news subsystem (a later WP).
- **Client robustness:** a rare empty API response (`prompt_tokens=0`, cost 0) is returned rather than
  raised/retried; the R4 `cost>0` assertion catches it downstream, but the metered client could raise or
  retry on an empty completion for the live path.
