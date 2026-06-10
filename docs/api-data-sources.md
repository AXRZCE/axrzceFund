# api-data-sources.md — Brokers, Market Data, Fundamentals, News: Integrations and Point-in-Time Discipline

**Status:** v1.0 — Foundation document (vendor facts verified June 2026; re-verify pricing at procurement)
**Depends on:** architecture.md (L1 design, ADR-6/7/8), configuration.md (§10 settings, blocking item: PIT fundamentals vendor)
**Feeds into:** backtesting-framework.md (cost/slippage models need this data), implementation-plan.md (Phase 1 unblocking)

---

## 1. Requirements (derived, not negotiable)

Hard requirements every data integration must satisfy before it touches L1:

- **R1 — Dual timestamps.** Every record stored with `as_of` (event time) and `available_at` (when *we could have known it*). If a vendor doesn't supply knowledge-time, `available_at = our ingestion time` and the source is marked `pit_grade: ingestion-stamped` (usable live, weaker for backtests).
- **R2 — Survivorship-free.** Historical universes must include delisted names, or the source is research-grade only.
- **R3 — Corporate-action correctness.** Splits/dividends handled with both adjusted and unadjusted series retained; adjustment factors stored, never applied destructively.
- **R4 — Replayability.** Raw payloads archived (cheap object storage) so any derived table can be rebuilt; vendor data revisions detectable via payload hashes.
- **R5 — Behind an interface.** No agent or protocol code imports a vendor SDK directly; everything goes through our adapters (`BrokerInterface`, `MarketDataInterface`, `FundamentalsInterface`, `DocumentsInterface`).
- **R6 — Budget known.** Each source has a monthly cost ceiling and a rate-limit budget documented here before integration.

---

## 2. Broker Adapters (execution + paper accounts)

### 2.1 Alpaca Paper — PRIMARY (ADR-8)
- **What it is:** API-first broker; a dedicated Paper-Only account type runs the full Trading API against a simulated portfolio. Same interface as live, so nothing in our stack changes if live capital is ever (much later) considered.
- **Auth/endpoints:** key/secret pair against `paper-api.alpaca.markets` (trading) and `data.alpaca.markets` (data). Official `alpaca-py` SDK; we wrap it, never call it raw (R5).
- **Capabilities used:** orders (market/limit/stop/bracket), positions, account, portfolio history, corporate-action notifications, websocket trade updates.
- **Known quirks to design around:**
  - **Paper fill realism is optimistic.** Paper fills simulate against the quote feed without our market impact; we therefore *also* compute our own modeled fill price (backtesting-framework.md slippage model) and log both. Realized-vs-modeled fill divergence is a standing dashboard metric.
  - Paper-Only accounts receive **IEX data only** (~2.5% of consolidated volume); fine for daily-cadence decisions, see §3.
  - Note: Pattern Day Trader rule enforcement was dropped by Alpaca as of June 2026 — irrelevant to our daily cadence, but don't build PDT logic we don't need.
- **Cost:** $0 (paper account + Basic data plan).

### 2.2 IBKR Paper — SECONDARY (validation mirror)
- **What it is:** Interactive Brokers paper account via Client Portal API or `ib_insync`/TWS. Institutional breadth; clunkier developer experience.
- **Role:** weekly mirror of a sample of Alpaca orders to cross-check fill simulation assumptions; fallback if Alpaca degrades. Not in the daily critical path during Phase 1.
- **Quirks:** session-based auth (gateway keep-alive needed), different symbology in corner cases (share classes, e.g., BRK.B vs BRK B) — adapter normalizes to our canonical ticker scheme.
- **Cost:** $0 paper; market-data subscriptions only if we later want its feeds (we don't, initially).

### 2.3 BrokerInterface contract (what upper layers see)
`submit(order_plan) → order_id`, `cancel(order_id)`, `positions()`, `account()`, `fills(since)` — plus a `simulate_fill(order, market_state)` hook the order manager calls to log modeled fills alongside broker-reported ones. Both adapters implement this contract; conformance tested by replaying a canned order script against both.

---

## 3. Market Data (prices, bars, quotes)

### Phase 1 — Alpaca Data API, IEX feed ($0)
- Daily + minute bars, latest quotes/trades, via the same vendor as execution (fewer moving parts).
- **Why IEX-only is acceptable now:** decisions are made at daily cadence on liquid S&P 500 names; IEX-derived bars track consolidated bars closely for large caps at EOD granularity. The known gap: intraday prints and exact session volume differ from the consolidated tape.
- **Architectural consequence:** our slippage model must not pretend to microstructure accuracy it doesn't have — costs are modeled conservatively (backtesting-framework.md owns parameters).

### Phase 2 — Polygon.io (paid) for consolidated data
- Full-market (SIP-sourced) aggregates, trades/quotes, websocket streaming; clean REST design; flat-rate plans (free tier: 5 calls/min, ~2yr history — development only; serious tiers roughly $29–$199+/mo depending on entitlements — verify at procurement).
- **Trigger to upgrade:** the moment we start *measuring* slippage seriously (Phase 2 exit criteria) or `monitor_interval` tightens below 60s, IEX-only stops being honest. Budget line: ≤ $250/mo.
- Alternative if tick-grade ever needed: Databento (institutional, usage-priced) — Phase 4 question at the earliest.

### Corporate actions & reference
- Phase 1: Alpaca corporate-actions endpoints + Sharadar ACTIONS table (comes with §4 choice) cross-checked nightly; disagreements halt the affected name (fail closed).
- Canonical symbology: our own `instrument_id` keyed to FIGI where available; ticker changes tracked as events, not overwrites.

---

## 4. Fundamentals — THE blocking decision, resolved

### Recommendation: **Sharadar Core US Fundamentals (SF1) via Nasdaq Data Link — PRIMARY**, EDGAR XBRL — verification & depth.

**Why Sharadar SF1 wins for us:**
- **True point-in-time:** data is time-indexed to the *filing date* (knowledge time) with restatement-inclusive and restatement-exclusive views — exactly our R1 `available_at` semantics, natively.
- **Survivorship-free:** 16,000+ US companies including 10,000+ delisted (R2), with up to ~28 years of history and ~150 standardized indicators; quarterly/TTM/annual dimensions.
- **Bundle adjacencies we'll use:** TICKERS (metadata/sector), ACTIONS (corporate actions cross-check), **S&P 500 constituent history** (point-in-time index membership — solves the P1 universe service cleanly), EVENTS (8-K), and optionally SEP (EOD prices as an independent price cross-check).
- **Practicalities:** updated twice daily; standard Nasdaq Data Link API/libraries; single-user licenses are among the cheapest professional PIT options (order of ~$50–100/mo class for core tables; confirm current pricing at checkout). Budget line: ≤ $150/mo.

**EDGAR XBRL (free) — the verification layer, not the primary:**
- Filings are the ground truth and `available_at` is the filing acceptance timestamp — perfect PIT semantics, $0.
- But: raw XBRL standardization (custom tags, restatements, fiscal-period alignment) is a project in itself; building "Sharadar quality" from EDGAR is weeks of work we shouldn't spend in Phase 1.
- **Role:** (a) VERIF-01's citation targets — memo claims cite actual filing documents; (b) spot-audit of Sharadar values (sampled nightly: N random datapoints traced back to filings); (c) full-text source for the RAG index (§5).

**Rejected for primary (with reasons):** FMP/EODHD/Alpha Vantage-class APIs — convenient and cheap but PIT semantics are weak-to-absent (restatements silently overwrite; `available_at` not modeled) → research-grade only under R1. Intrinio/S&P/FactSet-class — proper PIT but priced for institutions; unjustified at paper-trading scale.

### FundamentalsInterface contract
`fundamentals(ticker, dimension, as_known_at=decision_ts)` — the adapter translates our knowledge-time query into Sharadar's filing-date indexing; it is **impossible to request data the fund couldn't have known**, because the parameter is mandatory and defaulted to the cycle's `decision_ts`.

---

## 5. Filings, Transcripts, News (the RAG layer)

- **SEC EDGAR direct (free):** 10-K/10-Q/8-K/S-1 etc. via the official full-text and submissions APIs; rate limit 10 req/s with declared User-Agent; we mirror filings for our universe nightly into raw storage, then chunk/embed into the date-partitioned vector index (architecture L1). `available_at` = EDGAR acceptance datetime (excellent PIT).
- **News — Phase 1: Alpaca News API (Benzinga-sourced, included free):** real-time + historical headlines for our universe; `available_at` = ingestion time. Good enough for SENT-01's novelty classification at daily cadence.
- **News — Phase 2 option:** Polygon news (comes with the §3 upgrade) and/or a dedicated provider if event-driven escalations (P8) prove sensitive to headline latency. Decision deferred until we have escalation-latency data.
- **Earnings call transcripts:** no great free source. Phase 1: rely on 8-Ks/press releases + (where available) company IR PDFs ingested manually for debated names. Phase 2: procure a transcript API (e.g., FMP/Ninjas-class or API from a transcript specialist) — flagged as open item; PIT grade will be `ingestion-stamped`.

---

## 6. Ingestion Architecture & Schedules

| Pipeline | Source | Schedule | PIT grade |
|---|---|---|---|
| EOD bars + actions | Alpaca (P2: Polygon) | nightly 18:30 ET | vendor-stamped |
| Fundamentals delta | Sharadar SF1 | nightly post-17:30 ET update (+23:30 catch) | filing-date (native) |
| Universe/constituents | Sharadar SP500 table | nightly | native PIT |
| Filings mirror | EDGAR | nightly + intraday poll for held names | acceptance-stamped |
| News stream | Alpaca News websocket | continuous | ingestion-stamped |
| Raw payload archive | all of the above | with each run | hash-chained |

Rules: every pipeline is idempotent (re-runs converge); staleness sentinel per table feeds P1's freshness gate; any schema drift from a vendor fails the pipeline loudly rather than coercing silently.

## 7. Rate Limits & Cost Ledger

| Source | Limit (design budget) | $/mo (Phase 1 → 2) |
|---|---|---|
| Alpaca trading (paper) | 200 req/min — we use <10 | $0 |
| Alpaca data (IEX/news) | ample for daily cadence | $0 |
| Sharadar via NDL | API quota generous at our volume | ~$50–150 → same |
| EDGAR | 10 req/s hard, be polite | $0 |
| Polygon | n/a Phase 1 | $0 → ≤$250 |
| IBKR paper | session-based | $0 |
| **Total data budget** | | **≤$150 Phase 1, ≤$400 Phase 2** |

(Compare: LLM budget $50/day ≈ $1,100/mo — data is not the cost driver; don't economize on it where PIT quality is at stake.)

## 8. Failure & Fallback Policy
- Price feed down → cycle opens exit-only (P1 staleness gate); intraday monitors fall back to broker quote endpoints.
- Sharadar nightly missed → fundamentals memos run on last-known data with `stale: true` flag; FUND agents must disclose staleness in memos; second consecutive miss → fundamental memos suspended (candidates can still trade on other memos, at a haircut).
- EDGAR unreachable → VERIF-01 verifies against mirrored filings only; novelty claims requiring fresh filings are marked unverifiable (stripped).
- Vendor data *revision* detected (hash change on re-fetch) → both versions retained; event logged; backtests use original-as-of, live uses latest.

## 9. Open Items
- Earnings-transcript vendor (Phase 2 procurement; PIT grade will be ingestion-stamped).
- Polygon plan tier selection at Phase 2 trigger (depends on whether we want quotes or just aggregates).
- Borrow-availability data for shorts (Phase 1 proxy: easy-to-borrow list from broker; revisit if short book grows).
- Factor-model data source (Phase 2, with backtesting-framework.md).
