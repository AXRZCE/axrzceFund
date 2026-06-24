# WP0 — Repay R5 (vendor interface adapters): definition-of-done + rulings

**Committed BEFORE implementation code** (Phase 1 brief §1.1 / §5). Binding specs:
`api-data-sources.md` R5 + §2.3; `architecture.md` ADR-1/2/8 + L-layer boundaries.

## Definition of done (all must hold, demonstrable)
1. `data/interfaces/` exposes the four R5 ABCs: `MarketDataInterface`,
   `FundamentalsInterface`, `BrokerInterface`, `DocumentsInterface`.
2. Concrete adapters cover every Phase-0 vendor call: Alpaca IEX bars, Alpaca
   trading, and the full Sharadar SFA bundle (SF1 / SEP / SP500 / ACTIONS).
3. `data/ingestion.py`, `ops/broker_roundtrip.py`, `ops/verify_alpaca.py`,
   `ops/verify_sharadar.py` call **only** through adapters.
4. `tests/test_no_vendor_leakage.py` greps the tree and asserts the vendor SDK
   imports (`alpaca`, `nasdaqdatalink`) appear **only** under `data/interfaces/`. Green.
5. Replay determinism preserved: `ops/replay_check.py` passes; a fresh nightly
   ingest still produces a valid archive (raw payloads unchanged → byte-identical
   rebuild semantics intact).
6. Broker round-trip through the adapter = 10 orders / 0 mismatches / modeled-fill
   on all 10 (run at market hours; adapter correctness — account/positions —
   verifiable any time).
7. All existing tests green. Dead Windows-era `.cmd` files deleted.
8. ≥1 **real** integration run hits live Sharadar/Alpaca *through the adapter* and
   returns real rows (proves the adapter wraps the SDK, not a mock).

## Rulings (edge cases decided a priori, not after seeing results)

- **R-1 Interface structure (resolves the brief's "three adapters" vs four-by-function
  ambiguity).** The four ABCs are by *function*. Adapters:
  - `AlpacaMarketData(MarketDataInterface)` — IEX daily bars (live feed).
  - `AlpacaBroker(BrokerInterface)` — §2.3 contract.
  - `SharadarData(FundamentalsInterface, MarketDataInterface)` — the single Sharadar
    SFA-bundle wrapper: `get_fundamentals` (SF1) + `get_daily_bars` (SEP historical)
    + reference pulls `get_index_constituents` (SP500) and `get_corporate_actions`
    (ACTIONS).
  - `DocumentsInterface` ABC defined; **no concrete impl** (no Phase 1 agent reads
    filings) — and **no dead body / no `NotImplementedError`**; simply not instantiated.
  - *Deviation from the brief's literal name "SharadarFundamentals":* the Sharadar SFA
    bundle is one SDK serving four dataset types; splitting it across classes would
    create two `nasdaqdatalink` import sites for the same vendor. One `SharadarData`
    wrapper is cleaner and still satisfies R5 (SDK import in exactly one module).
    api-data-sources.md §4 treats the bundle as one source, so the spec supports this.
- **R-2 WP0 adapters return RAW vendor payloads (pandas DataFrames) to the ingestion
  layer**, preserving R4/G0.4: the raw archive + the existing pure transforms +
  byte-identical replay are unchanged. Deeper schema-normalization (vendor-neutral
  row dicts) is **deferred** — not required by any WP0 done-criterion, and doing it
  now would change the archived payload and weaken vendor-revision detection. The
  **broker** adapter, by contrast, returns clean domain types (str `order_id`, dict
  account/positions, list fills) per the §2.3 contract — no raw alpaca objects leak.
- **R-3 `test_no_vendor_leakage.py`** matches `^\s*(import|from)\s+(alpaca|nasdaqdatalink)`
  across `core/ data/ harness/ graphs/ agents/ ops/ tests/` and asserts every hit's
  path starts with `data/interfaces/`. A leak anywhere else fails the test.
- **R-4 Broker round-trip at market hours.** If the market is closed when WP0 lands,
  the 10-order round-trip is run at the next session's market window; adapter
  correctness is still proven now via real `account()`/`positions()` calls. This is
  noted in the readout, not silently skipped.
