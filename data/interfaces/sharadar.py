"""Sharadar SFA-bundle adapter (R5). The ONLY module that imports `nasdaqdatalink`
for Sharadar data. One vendor SDK → one wrapper covering all four bundle datasets
used in Phase 0/1: SF1 (fundamentals), SEP (historical prices), SP500 (index
constituents), ACTIONS (corporate actions). See WP0 ruling R-1.

Returns raw vendor DataFrames (ruling R-2) so the ingestion raw-archive and
byte-identical replay are unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import nasdaqdatalink as _ndl

from data.interfaces.base import FundamentalsInterface, MarketDataInterface


def _date_str(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class SharadarData(FundamentalsInterface, MarketDataInterface):
    """Wraps the Nasdaq Data Link Sharadar tables. Key from the
    NASDAQ_DATA_LINK_API_KEY env var only (configuration.md §10)."""

    def __init__(self) -> None:
        key = os.environ.get("NASDAQ_DATA_LINK_API_KEY")
        if not key:
            raise RuntimeError("NASDAQ_DATA_LINK_API_KEY not set (configuration.md §10)")
        _ndl.ApiConfig.api_key = key
        self._client = _ndl

    # ── FundamentalsInterface ────────────────────────────────────────────────
    def get_fundamentals(self, window_days: int = 7, dimension: str = "ARQ") -> Any:
        """SF1 rows updated within the trailing window (vendor `lastupdated`)."""
        return self._client.get_table(
            "SHARADAR/SF1", dimension=dimension,
            lastupdated={"gte": _date_str(window_days)}, paginate=True,
        )

    # ── MarketDataInterface (SEP historical prices) ──────────────────────────
    def get_daily_bars(self, tickers: Optional[list[str]] = None, window_days: int = 7) -> Any:
        """SEP survivorship-free EOD bars over the trailing window. `tickers` is
        accepted for the interface contract; SEP returns all names in the window."""
        params: dict[str, Any] = {"date": {"gte": _date_str(window_days)}, "paginate": True}
        if tickers:
            params["ticker"] = tickers
        return self._client.get_table("SHARADAR/SEP", **params)

    # ── Reference pulls (bundle-specific; used by ingestion) ─────────────────
    def get_index_constituents(self, index: str = "SP500") -> Any:
        """Point-in-time index constituent history (full table; small)."""
        return self._client.get_table(f"SHARADAR/{index}", paginate=True)

    def get_corporate_actions(self, window_days: int = 30) -> Any:
        """Corporate actions over the trailing window."""
        return self._client.get_table(
            "SHARADAR/ACTIONS", date={"gte": _date_str(window_days)}, paginate=True,
        )

    def ping(self, ticker: str = "AAPL") -> Any:
        """Lightweight entitlement check (one TICKERS row) — used by ops/verify_sharadar."""
        return self._client.get_table("SHARADAR/TICKERS", ticker=ticker)
