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

## Why it defers
Three independent reasons, in order of force. Any one suffices; together they are decisive.

### 1. Scope — an honest news path is a data-layer work package, not a WP2 agent patch
WP2's declared boundary is the in-scope P2 research agents + VERIF-01 + the fixture harness. A
PIT-correct SENT-01 needs an entire new data subsystem that does not exist:
- a `news`/`documents` table in `pit_store` + `insert_news`/`get_news` (mirroring `price_bars`);
- an `AlpacaDocuments(DocumentsInterface).get_news` in `data/interfaces/alpaca.py` — the only
  R5-legal home for the alpaca SDK (R2 forbids the agent calling the adapter directly);
- a `news` branch in `record_fixture` **and** `Fixture.audit_lookahead`;
- and conscious rewrites of two anti-hoax tests that currently *forbid* exactly this
  (`tests/test_interfaces.py` asserts `DocumentsInterface` stays abstract;
  `tests/test_no_vendor_leakage.py` polices the SDK boundary).

None of that is a WP2 deliverable. Building it to green one agent is scope creep into a later WP.

### 2. Hollowness — a day-one news fixture cannot do SENT-01's actual job
SENT-01's §3.5 mandate is **novelty detection** — "new info vs. an already-priced narrative" —
which requires a **trailing history of prior coverage** to judge what is new. A news store created
today has no such baseline, so `news_novelty` cannot be honestly computed: the memo would pass
schema/VERIF but be evidentially empty. This is the identical "greener-than-it-is" hazard that
Amendment A1 already refused for TECH-01 (which is why TECH-01 needed a ~252-day backfill first). A
meaningful SENT-01 needs a news history accumulated by forward-only live ingestion over time —
which by construction cannot exist on the day the table is first created.

### 3. Look-ahead — the only WP2-shaped news fixture is not PIT-safe
WP2 fixtures are **post-cutoff historical days** (FUND-TECH 2026-06-24; TECH-01 a 450-day SEP
backfill). The matching news variant is a **backfilled historical news day**, and that is
look-ahead-unsafe: the documented `available_at` is ingestion time (a forward-only stamp the fund
never generated for a past date), while the Alpaca API offers only *publisher* `created_at` /
`updated_at`. `updated_at` is an **unversioned revision** stamp (Benzinga retitles/corrects after
publish) and `News.symbols` tagging is itself revised — so using `created_at` as an `available_at`
proxy leaks corrected content and post-hoc symbol tags backward past the boundary. A SENT-01 memo on
such data would pass schema/VERIF but **fail the R2 look-ahead audit** — the deferral hides nothing;
it refuses to.

> **Honest caveat (what is *not* the reason):** a **live-forward** fixture — ingest real news *now*,
> stamp `available_at = now()`, set `decision_ts = today` — *is* PIT-honest: it clears R1 (today >
> the 2026-03-05 SENT-01 cutoff) and R2 (`now ≤ today`), and a forward-only ingestion stamp is the
> same grade the store already uses for SEP/IEX bars. So the block is **not** "news can never be
> PIT-stamped." It is that the live-forward path is precisely the out-of-scope build of reason 1 and
> would be hollow per reason 2. The defer rests on **scope + hollowness**, not on impossibility.

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
