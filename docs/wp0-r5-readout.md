# WP0 readout — R5 vendor interface adapters

**Branch:** `phase1/wp0-r5-repay`. **Done-criteria committed before code:** `465d72c`.
**Date:** 2026-06-24.

## What changed
- New `data/interfaces/`: four R5 ABCs (`MarketDataInterface`, `FundamentalsInterface`,
  `BrokerInterface`, `DocumentsInterface`) + concrete adapters `AlpacaMarketData`
  (IEX bars + latest trade), `AlpacaBroker` (§2.3 contract), `SharadarData` (SFA
  bundle: SF1 / SEP / SP500 / ACTIONS). `DocumentsInterface` is ABC-only (ruling R-1).
- `data/ingestion.py`, `ops/broker_roundtrip.py`, `ops/verify_alpaca.py`,
  `ops/verify_sharadar.py` refactored to call **only** through adapters.
- Deleted dead Windows-era files: `ops/{g05_run,nightly_ingest,wake_test}.cmd`.
- New tests: `test_no_vendor_leakage.py` (R5 grep gate), `test_interfaces.py`
  (contracts are true ABCs).

## Evidence (each done-criterion)
| Criterion | Result |
|---|---|
| 4 ABCs + adapters cover every Phase-0 vendor call | ✅ |
| Consumers call only through adapters | ✅ |
| `test_no_vendor_leakage` green (SDKs only under `data/interfaces/`) | ✅ regex covers `import`/aliased/`from`/submodule; ignores our own `data.interfaces.alpaca` |
| **Adapter behavior-preserving** (the load-bearing check) | ✅ `SharadarData.get_daily_bars` **byte-identical** to the raw `nasdaqdatalink.get_table` (shape, dtype, row order, values) — proven by direct adapter-vs-SDK frame compare |
| Replay determinism preserved | ✅ `replay_check` on the adapter-produced archive `ingest_20260624_ac4aef` = byte-identical rebuild, all 4 tables hash-match |
| Nightly ingest through adapters | ✅ `all_ok`, PIT 0, valid archive |
| Real integration through adapter (not mock) | ✅ Sharadar 5/5 datasets; Alpaca account + 9 real IEX bars (AAPL 293.32 @ 06-24) |
| All existing tests green | ✅ **114/114** |
| `DocumentsInterface` is a true ABC | ✅ instantiation raises `TypeError` (test) |

## One criterion PENDING — broker write-path (ruling R-4)
The reads (`account`, `positions`, `clock`, `fills`) are proven. The **write-path
(`submit`/`cancel`) is exercised only by the 10-order round-trip, which needs market
hours** — and the market was closed at WP0 completion (next open **2026-06-25
09:30 ET**). Per pre-committed ruling R-4 this is deferred, not skipped.

**Recommendation:** review/merge this PR on the read+refactor evidence; I run the
10-order round-trip through `AlpacaBroker` at the 06-25 open and confirm
PASS (10 orders / 0 mismatches / modeled-fill on all 10) before WP1 work is merged.
**Hard dependency for WP4** (where orders actually flow): WP4 must NOT assume the
broker write-path is validated until that round-trip is green.

## Note
The laptop nightly-ingest recon flagged SF1 43119→18945 — a **cross-baseline
artifact** (laptop's prior run was 06-15, 9 days + different `lastupdated` window
ago), not a coverage change. The VM is the canonical night-over-night soak host.
