"""Nightly ingestion jobs — api-data-sources.md §6, G0.3 soak.

One job per dataset, each:
  - idempotent (INSERT OR REPLACE over a trailing window — re-runs converge)
  - dual-timestamped per R1 (native knowledge time where the vendor supplies it,
    ingestion-stamped otherwise)
  - recorded in the PIT store's ingestion_audit table
  - appended to the hash-chained event log (cycle_id = run_id)

Path separation per api-data-sources.md §3 (amendment): Sharadar SEP is the
backtest/historical price series; Alpaca IEX is the LIVE feed only. They write to
the same price_bars table but with distinct `source` values ('sep' vs 'iex') and
are ingested by separate jobs — never mixed.

Keys: NASDAQ_DATA_LINK_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY from the
environment only (configuration.md §10) — never logged, never stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from core.event_log import EventLog
from data.pit_store import PITStore

logger = structlog.get_logger()

# Default watchlist for the Alpaca live-bar job if the universe table is empty
# (pre-universe-soak bootstrap). Replaced by SP500 constituents once ingested.
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "UNH"]


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


def _ndl():
    import nasdaqdatalink as ndl
    import os
    key = os.environ.get("NASDAQ_DATA_LINK_API_KEY")
    if not key:
        raise RuntimeError("NASDAQ_DATA_LINK_API_KEY not set (configuration.md §10)")
    ndl.ApiConfig.api_key = key
    return ndl


# ── Sharadar jobs ──────────────────────────────────────────────────────────────

def ingest_sep(store: PITStore, run_id: str, window_days: int = 7) -> JobResult:
    """SEP daily bars (backtest/historical price series) — trailing window, all tickers."""
    job, source = "sep_daily_bars", "sep"
    try:
        ndl = _ndl()
        df = ndl.get_table(
            "SHARADAR/SEP",
            date={"gte": _date_str(window_days)},
            paginate=True,
        )
        now = _now_utc()
        rows = [
            dict(ticker=r.ticker, as_of=f"{r.date:%Y-%m-%d}T00:00:00+00:00",
                 available_at=now, pit_grade="ingestion-stamped",
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=int(r.volume) if r.volume == r.volume else None,
                 source=source)
            for r in df.itertuples()
        ]
        n = store.insert_price_bars(rows) if rows else 0
        store.record_ingestion(run_id, "price_bars(sep)", n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, "price_bars(sep)", 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


def ingest_sf1(store: PITStore, run_id: str, window_days: int = 7,
               dimension: str = "ARQ") -> JobResult:
    """SF1 fundamentals delta — rows the vendor updated in the trailing window.
    available_at = datekey (filing date — native knowledge time)."""
    job, source = "sf1_fundamentals", "sharadar_sf1"
    try:
        ndl = _ndl()
        df = ndl.get_table(
            "SHARADAR/SF1",
            dimension=dimension,
            lastupdated={"gte": _date_str(window_days)},
            paginate=True,
        )
        indicators = ["eps", "revenue", "netinc", "equity", "assets", "fcf"]
        rows = []
        for r in df.itertuples():
            # as_of = reportperiod (the ACTUAL fiscal period end). Sharadar's
            # calendardate is a normalized calendar-quarter LABEL and can postdate
            # the filing for off-calendar fiscal years (e.g. PVH: fiscal Q ends
            # early Aug, filed Sep, labeled Sep 30) — using it as event time made
            # knowledge precede the event. reportperiod <= datekey always.
            as_of = f"{r.reportperiod:%Y-%m-%d}T00:00:00+00:00"
            available_at = f"{r.datekey:%Y-%m-%d}T00:00:00+00:00"
            period = f"{r.calendardate:%Y-%m}"
            for ind in indicators:
                v = getattr(r, ind, None)
                if v is None or v != v:  # NaN
                    continue
                rows.append(dict(
                    ticker=r.ticker, dimension=dimension, period=period,
                    as_of=as_of, available_at=available_at, pit_grade="native",
                    indicator=ind.upper(), value=float(v),
                ))
        n = store.insert_fundamentals(rows) if rows else 0
        store.record_ingestion(run_id, "fundamentals", n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, "fundamentals", 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


def ingest_sp500(store: PITStore, run_id: str) -> JobResult:
    """SP500 constituent history — full history (idempotent upsert; the table is
    small). 'added'/'current' → in_index True at that date; 'removed' → False."""
    job, source = "sp500_universe", "sharadar_sp500"
    try:
        ndl = _ndl()
        df = ndl.get_table("SHARADAR/SP500", paginate=True)
        now = _now_utc()
        rows = []
        for r in df.itertuples():
            action = str(r.action).lower()
            if action in ("added", "current"):
                in_index = True
            elif action in ("removed", "historical"):
                in_index = False
            else:
                continue
            rows.append(dict(
                index_name="SP500", ticker=r.ticker,
                as_of=f"{r.date:%Y-%m-%d}T00:00:00+00:00",
                available_at=now, pit_grade="ingestion-stamped",
                in_index=in_index,
            ))
        n = store.insert_universe(rows) if rows else 0
        store.record_ingestion(run_id, "universe_membership", n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, "universe_membership", 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


def ingest_actions(store: PITStore, run_id: str, window_days: int = 30) -> JobResult:
    """Corporate actions — trailing window (cross-checked vs Alpaca nightly in P1+)."""
    job, source = "corporate_actions", "sharadar_actions"
    try:
        ndl = _ndl()
        df = ndl.get_table(
            "SHARADAR/ACTIONS",
            date={"gte": _date_str(window_days)},
            paginate=True,
        )
        now = _now_utc()
        rows = [
            dict(ticker=r.ticker, as_of=f"{r.date:%Y-%m-%d}T00:00:00+00:00",
                 available_at=now, pit_grade="ingestion-stamped",
                 action=str(r.action),
                 value=float(r.value) if r.value == r.value else None,
                 contraticker=str(r.contraticker) if r.contraticker == r.contraticker else None,
                 source=source)
            for r in df.itertuples()
        ]
        n = store.insert_corporate_actions(rows) if rows else 0
        store.record_ingestion(run_id, "corporate_actions", n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, "corporate_actions", 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


# ── Alpaca live-feed job (separate path — never used for backtests) ───────────

def ingest_iex_bars(store: PITStore, run_id: str, window_days: int = 7) -> JobResult:
    """Alpaca IEX daily bars for the current watchlist (live feed capture)."""
    job, source = "iex_daily_bars", "iex"
    try:
        import os
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Alpaca keys not set (configuration.md §10)")

        tickers = store.get_universe("SP500", as_known_at=_now_utc()) or DEFAULT_WATCHLIST

        client = StockHistoricalDataClient(api_key=key, secret_key=secret)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=window_days)
        req = StockBarsRequest(symbol_or_symbols=tickers, timeframe=TimeFrame.Day,
                               start=start, end=end, feed="iex")
        resp = client.get_stock_bars(req)

        now = _now_utc()
        rows = []
        for symbol, bars in resp.data.items():
            for bar in bars:
                rows.append(dict(
                    ticker=symbol, as_of=bar.timestamp.astimezone(timezone.utc).isoformat(),
                    available_at=now, pit_grade="ingestion-stamped",
                    open=float(bar.open), high=float(bar.high), low=float(bar.low),
                    close=float(bar.close), volume=int(bar.volume), source=source,
                ))
        n = store.insert_price_bars(rows) if rows else 0
        store.record_ingestion(run_id, "price_bars(iex)", n, source, "ok")
        return JobResult(job, source, n, "ok")
    except Exception as e:
        store.record_ingestion(run_id, "price_bars(iex)", 0, source, "error", str(e))
        return JobResult(job, source, 0, "error", str(e))


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_nightly(store: PITStore, event_log: EventLog, run_id: str) -> dict:
    """Run all five jobs, append every result to the event log, run the PIT audit.

    Returns the run summary dict (also what the nightly runner persists to JSON).
    """
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
        "all_ok": all(r.status == "ok" for r in results) and not audit_violations,
    }

    event_log.append(
        event_type="ingestion_run",
        cycle_id=run_id,
        payload=summary,
    )
    logger.info("nightly_ingestion_done", run_id=run_id, all_ok=summary["all_ok"])
    return summary
