# WP2 — SENT-01 logged defer ruling

**Decision (2026-07-01): SENT-01 is DEFERRED at WP2.** It ships flagged/deferred, not faked. This is
the pre-committed fallback in [wp2-real-agents-done-criteria.md](wp2-real-agents-done-criteria.md)
(“If no PIT-correct news source is wireable, sequence SENT-01 last and ship it flagged/deferred
rather than fake sentiment”) and [phase1-completion-plan.md](phase1-completion-plan.md) §WP2 item 4.

FUND-TECH and TECH-01 — the two research agents with a PIT-correct data path in `pit_store` — are
built and proven. SENT-01 is the third; it has **no such path**, and manufacturing one to green the
milestone would violate the WP2 rulings. The details, so the deferral is auditable:

## What IS available
- The Alpaca News API is reachable and its shape is known: `alpaca.data.historical.news.NewsClient.
  get_news(NewsRequest)` → `GET /v1beta1/news`, returning `News{id, headline, summary, source,
  url, created_at, updated_at, symbols, author, content}` (source e.g. `Benzinga`). The SDK is
  installed; `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` are set on the dev box.
- The output schema is already in place for when SENT-01 lands: `SentMemo` / `SentimentBlock`
  (`graphs/state.py`), and VERIF-01 already maps `SENT-01 → SentMemo` (`graphs/verif01.py`), so R3
  needs no new code. The manifest pins `SENT-01 → openai/gpt-5.4` (cutoff 2026-03-05,
  provider `only:[openai]`).

## Why it defers (the PIT thorn)
A WP2 fixture is a **post-cutoff historical decision day**, read through `pit_store` as-of
`decision_ts`, with every row's `available_at <= decision_ts` (R2). News cannot honestly satisfy
this for a historical date:

1. **No PIT news store.** `pit_store` has `price_bars`, `fundamentals`, `universe_membership`,
   `corporate_actions` — **no news/documents table and no `get_news` read**. `DocumentsInterface`
   (`data/interfaces/base.py`) is deliberately abstract (an anti-hoax test asserts it stays so).
   `record_fixture` / `Fixture.audit_lookahead` have no `news` branch. R2 mandates reads flow
   through `pit_store`; a raw adapter call from the agent would break R2 and the R5 vendor-leakage
   boundary.
2. **No honest `available_at` for a past date.** The documented news `available_at` is *ingestion
   time* — the wall-clock when the fund first saw the article live (`pit_grade='ingestion-stamped'`,
   forward-only). For a historical/backfilled day the fund never ingested that news at that date, so
   there is **no honest ingestion-time stamp**. The API offers only *publisher* timestamps
   (`created_at`, `updated_at`) — not the fund's knowledge time.
3. **Publisher timestamps leak look-ahead.** Using `created_at` as an `available_at` proxy is a
   look-ahead risk: `updated_at` is an **unversioned revision** stamp (Benzinga retitles/corrects
   after publish, overwriting `updated_at`), so a corrected summary would be read as if known at the
   original time; and `News.symbols` tagging is itself revised, so “news for X” can pull articles
   tagged to X only *after* the boundary. A `SENT-01` memo built on such data would pass schema/VERIF
   but **fail the R2 look-ahead audit** — the deferral moves the failure nowhere; it just refuses to
   hide it.

Verdict: a PIT-correct SENT-01 fixture is **not honestly constructible for a post-cutoff historical
day** with the current data layer. Faking it (proxy `available_at`, or grounding SENT-01 on
price/fundamentals it is not meant to read) is exactly the hoax the WP2 anti-hoax contract forbids.

## Un-defer condition (what lands SENT-01 later)
SENT-01 becomes buildable — as its own scoped work, not a WP2 patch — when a **PIT-correct news
source** exists. Two honest routes:
- **Live-forward path (preferred, a later WP):** a live ingestion stream that stamps
  `available_at = now()` forward-only, a `news` table + `insert_news`/`get_news` in `pit_store`
  (mirroring `price_bars`), a `get_news` impl in `data/interfaces/alpaca.py` (the only R5-legal home
  for the alpaca SDK), a `news` branch in `record_fixture` + `Fixture.audit_lookahead`, and a
  conscious update to `tests/test_interfaces.py` (which asserts `DocumentsInterface` stays abstract)
  and `tests/test_no_vendor_leakage.py`. A fixture with `decision_ts` at/after the ingestion time is
  then genuinely PIT-clean.
- **Ruled fixture policy:** a separate owner ruling on a news `available_at` convention for backtests
  (with an explicit revision/retention policy) — only if it can be made look-ahead-free.

Then: record a SENT-01 golden fixture (`decision_ts` after 2026-03-05, grounding on `news:` doc_ids),
add `run_sent_01` (a `run_fund_tech` clone emitting `sentiment_block`), and
`tests/integration/test_sent_01.py` mirroring TECH-01 (R1 `for_roles=['SENT-01']`, R3/R4/R5 +
grounding, provider `only:[openai]`).

## WP2 outcome
WP2 closes with **two proven research agents** (FUND-TECH `d34ae72`, TECH-01 `10ade17`) and **SENT-01
deferred by this ruling**, matching the completion bar (“the agents — or two + a logged SENT defer”).
The marker of the deferral is `tests/integration/test_sent_01.py` (an explicit module-level skip
citing this doc). No sentiment is fabricated.
