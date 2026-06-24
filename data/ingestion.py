"""Nightly ingestion jobs — api-data-sources.md §6, G0.3 soak, R4 replayability.

One job per dataset, each:
  - idempotent (INSERT OR REPLACE over a trailing window — re-runs converge)
  - dual-timestamped per R1 (native knowledge time where the vendor supplies it,
    ingestion-stamped otherwise)
  - raw payload archived (R4) to var/raw_archive/<run_id>/ with a SHA256 manifest,
    so any derived table can be rebuilt byte-identically (G0.4 replay drill)
  - recorded in the PIT store's ingestion_audit table
  - appended to the hash-chained event log (cycle_id = run_id)

Structure: fetch (network) → archive (raw parquet + manifest) → transform (PURE
function of (raw, stamp) — this is what the G0.4 replay check re-executes) →
insert. Transforms must stay deterministic: same archived raw + same stamp ⇒ the
same rows, byte for byte.

Path separation per api-data-sources.md §3 (amendment): Sharadar SEP is the
backtest/historical price series; Alpaca IEX is the LIVE feed only. Same
price_bars table, distinct `source` values ('sep' vs 'iex'), separate jobs.

Keys: NASDAQ_DATA_LINK_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY from the
environment only (configuration.md §10) — never logged, never stored.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

from core.event_log import EventLog
from data.pit_store import PITStore

logger = structlog.get_logger()

ARCHIVE_ROOT = Path("var/raw_archive")

# Default watchlist for the Alpaca live-bar job if the universe table is empty
# (pre-universe-soak bootstrap). Replaced by SP500 constituents once ingested.
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "UNH"]

SF1_INDICATORS = ["eps", "revenue", "netinc", "equity", "assets", "fcf"]


@dataclass
class JobResult:
    job: str
    source: str
    rows: int
    status: str           # 'ok' | 'error'
    error: Optional[str] = None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_str(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# Vendor access is via the R5 adapters only (data/interfaces). Lazy singletons so a
# missing key surfaces at first fetch, not at import.
_sharadar = None
_alpaca_md = None


def _sharadar_adapter():
    global _sharadar
    if _sharadar is None:
        from data.interfaces import SharadarData
        _sharadar = SharadarData()
    return _sharadar


def _alpaca_md_adapter():
    global _alpaca_md
    if _alpaca_md is None:
        from data.interfaces import AlpacaMarketData
        _alpaca_md = AlpacaMarketData()
    return _alpaca_md


# ── Raw archive (R4) ───────────────────────────────────────────────────────────

def archive_raw(run_id: str, job: str, df, stamp: str) -> dict:
    """Persist a job's raw payload as parquet + manifest entry (R4 replayability).

    The manifest records the ingestion stamp used as `available_at` for
    ingestion-stamped tables, so the G0.4 replay reproduces the EXACT rows.
    """
    run_dir = ARCHIVE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    pq = run_dir / f"{job}.parquet"
    df.to_parquet(pq, index=False)
    sha = hashlib.sha256(pq.read_bytes()).hexdigest()

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "run_id": run_id, "jobs": {},
    }
    manifest["jobs"][job] = {
        "file": pq.name, "sha256": sha, "stamp": stamp, "raw_rows": int(len(df)),
        "archived_at": _now_utc(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("raw_archived", job=job, rows=len(df), sha256=sha[:12])
    return manifest["jobs"][job]


# ── Pure transforms (raw, stamp) -> rows — re-executed by the G0.4 replay ─────

def transform_sep(df, stamp: str) -> list[dict[str, Any]]:
    return [
        dict(ticker=r.ticker, as_of=f"{r.date:%Y-%m-%d}T00:00:00+00:00",
             available_at=stamp, pit_grade="ingestion-stamped",
             open=float(r.open), high=float(r.high), low=float(r.low),
             close=float(r.close), volume=int(r.volume) if r.volume == r.volume else None,
             source="sep")
        for r in df.itertuples()
    ]


def transform_sf1(df, stamp: str, dimension: str = "ARQ") -> list[dict[str, Any]]:
    """available_at = datekey (filing date — native knowledge time); `stamp` unused
    but kept for the uniform transform signature."""
    rows: list[dict[str, Any]] = []
    for r in df.itertuples():
        # as_of = reportperiod (the ACTUAL fiscal period end). Sharadar's
        # calendardate is a normalized calendar-quarter LABEL and can postdate the
        # filing for off-calendar fiscal years (PVH) — using it as event time made
        # knowledge precede the event. reportperiod <= datekey always.
        as_of = f"{r.reportperiod:%Y-%m-%d}T00:00:00+00:00"
        available_at = f"{r.datekey:%Y-%m-%d}T00:00:00+00:00"
        period = f"{r.calendardate:%Y-%m}"
        for ind in SF1_INDICATORS:
            v = getattr(r, ind, None)
            if v is None or v != v:  # NaN
                continue
            rows.append(dict(
                ticker=r.ticker, dimension=dimension, period=period,
                as_of=as_of, available_at=available_at, pit_grade="native",
                indicator=ind.upper(), value=float(v),
            ))
    return rows


def transform_sp500(df, stamp: str) -> list[dict[str, Any]]:
    """Constituent history. available_at = the CHANGE DATE (native knowledge time),
    NOT the ingestion stamp: an index membership change is public/effective on its
    date, so that is when we'd have known it. Stamping all of history with now()
    (a) collapses the knowledge dimension and (b) makes get_universe's "latest row
    per ticker by available_at" resolve on an arbitrary tie-break among equal
    timestamps — which silently emptied the universe and dropped IEX coverage from
    ~500 names to the 10-name fallback (caught by soak reconciliation 2026-06-15)."""
    rows = []
    for r in df.itertuples():
        action = str(r.action).lower()
        if action in ("added", "current"):
            in_index = True
        elif action in ("removed", "historical"):
            in_index = False
        else:
            continue
        change_date = f"{r.date:%Y-%m-%d}T00:00:00+00:00"
        rows.append(dict(
            index_name="SP500", ticker=r.ticker,
            as_of=change_date,
            available_at=change_date, pit_grade="native",
            in_index=in_index,
        ))
    return rows


def transform_actions(df, stamp: str) -> list[dict[str, Any]]:
    return [
        dict(ticker=r.ticker, as_of=f"{r.date:%Y-%m-%d}T00:00:00+00:00",
             available_at=stamp, pit_grade="ingestion-stamped",
             action=str(r.action),
             value=float(r.value) if r.value == r.value else None,
             contraticker=str(r.contraticker) if r.contraticker == r.contraticker else None,
             source="sharadar_actions")
        for r in df.itertuples()
    ]


def transform_iex(df, stamp: str) -> list[dict[str, Any]]:
    """df columns: symbol, timestamp (ISO str), open, high, low, close, volume."""
    return [
        dict(ticker=r.symbol, as_of=str(r.timestamp),
             available_at=stamp, pit_grade="ingestion-stamped",
             open=float(r.open), high=float(r.high), low=float(r.low),
             close=float(r.close), volume=int(r.volume), source="iex")
        for r in df.itertuples()
    ]


TRANSFORMS = {
    "sep_daily_bars": ("price_bars", transform_sep),
    "sf1_fundamentals": ("fundamentals", transform_sf1),
    "sp500_universe": ("universe_membership", transform_sp500),
    "corporate_actions": ("corporate_actions", transform_actions),
    "iex_daily_bars": ("price_bars", transform_iex),
}

INSERTERS = {
    "price_bars": "insert_price_bars",
    "fundamentals": "insert_fundamentals",
    "universe_membership": "insert_universe",
    "corporate_actions": "insert_corporate_actions",
}


def _run_job(store: PITStore, run_id: str, job: str, source: str,
             audit_table: str, fetch) -> JobResult:
    """fetch() -> raw df; then archive -> transform -> insert -> audit."""
    try:
        df = fetch()
        stamp = _now_utc()
        archive_raw(run_id, job, df, stamp)
        table, transform = TRANSFORMS[job]
        rows = transform(df, stamp)
        n = getattr(store, INSERTERS[table])(rows) if rows else 0
        store.record_ingestion(run_id, audit_table, n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, audit_table, 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


# ── Jobs ───────────────────────────────────────────────────────────────────────

def ingest_sep(store: PITStore, run_id: str, window_days: int = 7) -> JobResult:
    """SEP daily bars (backtest/historical price series) — trailing window, all tickers."""
    return _run_job(
        store, run_id, "sep_daily_bars", "sep", "price_bars(sep)",
        lambda: _sharadar_adapter().get_daily_bars(window_days=window_days),
    )


def ingest_sf1(store: PITStore, run_id: str, window_days: int = 7) -> JobResult:
    """SF1 fundamentals delta — rows the vendor updated in the trailing window."""
    return _run_job(
        store, run_id, "sf1_fundamentals", "sharadar_sf1", "fundamentals",
        lambda: _sharadar_adapter().get_fundamentals(window_days=window_days, dimension="ARQ"),
    )


def ingest_sp500(store: PITStore, run_id: str) -> JobResult:
    """SP500 constituent history — full history (small table, idempotent upsert)."""
    return _run_job(
        store, run_id, "sp500_universe", "sharadar_sp500", "universe_membership",
        lambda: _sharadar_adapter().get_index_constituents("SP500"),
    )


def ingest_actions(store: PITStore, run_id: str, window_days: int = 30) -> JobResult:
    """Corporate actions — trailing window (cross-checked vs Alpaca nightly in P1+)."""
    return _run_job(
        store, run_id, "corporate_actions", "sharadar_actions", "corporate_actions",
        lambda: _sharadar_adapter().get_corporate_actions(window_days=window_days),
    )


def _fetch_iex(store: PITStore, window_days: int):
    """Resolve the current universe (PIT) and fetch its IEX bars through the adapter."""
    tickers = store.get_universe("SP500", as_known_at=_now_utc()) or DEFAULT_WATCHLIST
    return _alpaca_md_adapter().get_daily_bars(tickers, window_days)


def ingest_iex_bars(store: PITStore, run_id: str, window_days: int = 7) -> JobResult:
    """Alpaca IEX daily bars for the current watchlist (live-feed capture only)."""
    return _run_job(
        store, run_id, "iex_daily_bars", "iex", "price_bars(iex)",
        lambda: _fetch_iex(store, window_days),
    )


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_nightly(store: PITStore, event_log: EventLog, run_id: str) -> dict:
    """Run all five jobs, append every result to the event log, run the PIT audit."""
    started = _now_utc()
    results = [
        ingest_sep(store, run_id),
        ingest_sf1(store, run_id),
        ingest_sp500(store, run_id),
        ingest_actions(store, run_id),
        ingest_iex_bars(store, run_id),
    ]

    audit_violations = store.audit_future_data()
    staleness = {
        t: store.staleness_check(t)
        for t in ("price_bars", "fundamentals", "universe_membership", "corporate_actions")
    }

    summary = {
        "run_id": run_id,
        "started": started,
        "finished": _now_utc(),
        "jobs": [vars(r) for r in results],
        "pit_audit_violations": [str(v) for v in audit_violations],
        "staleness": staleness,
        "raw_archive": str(ARCHIVE_ROOT / run_id),
        "all_ok": all(r.status == "ok" for r in results) and not audit_violations,
    }

    event_log.append(
        event_type="ingestion_run",
        cycle_id=run_id,
        payload=summary,
    )
    logger.info("nightly_ingestion_done", run_id=run_id, all_ok=summary["all_ok"])
    return summary
