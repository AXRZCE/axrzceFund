"""Abstract vendor contracts (R5). No vendor SDK is imported here — these are the
boundary the rest of the codebase depends on instead of any concrete vendor.

WP0 ruling R-2: market/fundamentals methods return the RAW vendor payload (a pandas
DataFrame) so the ingestion raw-archive and byte-identical replay (R4/G0.4) are
unchanged. The broker contract returns clean domain types (str/dict/list) per
api-data-sources.md §2.3 — no raw broker objects leak upward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class MarketDataInterface(ABC):
    """Daily price/bar data. Implementations: AlpacaMarketData (IEX live feed),
    SharadarData (SEP historical/backtest series)."""

    @abstractmethod
    def get_daily_bars(self, tickers: Optional[list[str]], window_days: int) -> Any:
        """Return daily OHLCV bars over a trailing `window_days` window as the raw
        vendor DataFrame. `tickers=None` means the vendor's natural full set
        (Sharadar SEP returns all names in the window); a list restricts to those
        symbols (Alpaca IEX fetches per-symbol)."""

    def get_latest_quote(self, symbol: str) -> dict:
        """Latest NBBO quote {bid, ask, spread_bps, ts} — READ-only market data (the WP4 wall
        blocks broker WRITES, not reads). Used by WP6 R2 quote logging for the cost-model
        recalibration. Optional: implementations without a quote feed raise."""
        raise NotImplementedError(f"{type(self).__name__} has no quote feed")


class FundamentalsInterface(ABC):
    """Point-in-time fundamentals (Sharadar SF1). available_at = filing date."""

    @abstractmethod
    def get_fundamentals(self, window_days: int, dimension: str = "ARQ") -> Any:
        """Return the fundamentals rows the vendor updated within the trailing
        `window_days` (by vendor lastupdated), as the raw vendor DataFrame."""


class BrokerInterface(ABC):
    """Execution + account access (api-data-sources.md §2.3). Clean domain types
    only — callers never see a raw broker SDK object."""

    @abstractmethod
    def submit(self, order_plan: dict) -> str:
        """Submit an order described by a vendor-neutral plan dict
        (keys: symbol, qty, side['buy'|'sell'], type['market'|'limit'], tif,
        optional limit_price). Returns the broker order_id as a string."""

    @abstractmethod
    def cancel(self, order_id: str) -> None:
        """Cancel an open order by id."""

    @abstractmethod
    def positions(self) -> list[dict]:
        """Current open positions as dicts (keys incl. symbol, qty, market_value)."""

    @abstractmethod
    def account(self) -> dict:
        """Account snapshot (keys: status, buying_power, portfolio_value, cash,
        currency)."""

    @abstractmethod
    def fills(self, since: Optional[str] = None) -> list[dict]:
        """Filled orders since an ISO timestamp (None = recent), as dicts."""

    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """Status of one order (keys: order_id, status, filled_qty,
        filled_avg_price) — for the order manager to poll a fill."""

    @abstractmethod
    def simulate_fill(self, order: dict, market_state: dict) -> float:
        """Our modeled fill price for an order given market_state (e.g.
        {'price': <latest trade>}), so realized-vs-modeled divergence can be logged
        alongside the broker fill (backtesting-framework.md §3.3)."""

    @abstractmethod
    def is_market_open(self) -> bool:
        """Whether the market is currently open (for the market-hours guard)."""


class DocumentsInterface(ABC):
    """Filings / news documents. Contract defined for Phase 1 completeness; no
    concrete implementation yet (no in-scope Phase 1 agent reads filings — see WP0
    ruling R-1). Deliberately not instantiated."""

    @abstractmethod
    def get_filings(self, ticker: str, as_known_at: str) -> Any:
        """Filings for `ticker` knowable as of `as_known_at` (PIT)."""

    @abstractmethod
    def get_news(self, ticker: str, as_known_at: str) -> Any:
        """News items for `ticker` knowable as of `as_known_at` (PIT)."""
