"""Alpaca adapter (R5). The ONLY module that imports the `alpaca` SDK.

`AlpacaMarketData` (IEX live daily bars + latest trade) implements
MarketDataInterface; `AlpacaBroker` implements the §2.3 BrokerInterface contract
with clean domain types (no raw alpaca objects leak upward).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)

from data.interfaces.base import BrokerInterface, MarketDataInterface

_HALF_SPREAD_BPS = 1.0  # mega-cap floor (backtesting-framework.md §3.3)


def _keys() -> tuple[str, str]:
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca keys not set (configuration.md §10)")
    return key, secret


class AlpacaMarketData(MarketDataInterface):
    """IEX live feed (paper-account entitlement) via the Alpaca data API."""

    def __init__(self) -> None:
        key, secret = _keys()
        self._client = StockHistoricalDataClient(api_key=key, secret_key=secret)

    def get_daily_bars(self, tickers: Optional[list[str]], window_days: int = 7) -> Any:
        """IEX daily bars for `tickers` over the trailing window, as a DataFrame with
        columns [symbol, timestamp, open, high, low, close, volume]."""
        if not tickers:
            raise ValueError("AlpacaMarketData.get_daily_bars requires explicit tickers")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=window_days)
        resp = self._client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=tickers, timeframe=TimeFrame.Day,
            start=start, end=end, feed="iex"))
        records = []
        for symbol, bars in resp.data.items():
            for bar in bars:
                records.append(dict(
                    symbol=symbol,
                    timestamp=bar.timestamp.astimezone(timezone.utc).isoformat(),
                    open=float(bar.open), high=float(bar.high), low=float(bar.low),
                    close=float(bar.close), volume=int(bar.volume),
                ))
        return pd.DataFrame.from_records(
            records, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

    def get_latest_trade(self, symbol: str) -> float:
        """Latest IEX trade price for `symbol` (used for modeled-fill marking)."""
        resp = self._client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex"))
        return float(resp[symbol].price)

    def get_latest_quote(self, symbol: str) -> dict:
        """Latest IEX NBBO quote — READ-only (WP6 R2 quote logging for cost recalibration)."""
        resp = self._client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol, feed="iex"))
        q = resp[symbol]
        bid, ask = float(q.bid_price), float(q.ask_price)
        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / mid * 1e4) if mid > 0 else None
        return dict(bid=bid, ask=ask, mid=mid, spread_bps=spread_bps,
                    ts=q.timestamp.isoformat() if q.timestamp else None)


class AlpacaBroker(BrokerInterface):
    """Alpaca paper trading (ADR-8). Defaults to the paper endpoint."""

    def __init__(self, paper: bool = True) -> None:
        key, secret = _keys()
        self._trading = TradingClient(api_key=key, secret_key=secret, paper=paper)

    def submit(self, order_plan: dict) -> str:
        side = OrderSide.BUY if order_plan["side"] == "buy" else OrderSide.SELL
        tif = TimeInForce(order_plan.get("tif", "day"))
        if order_plan.get("type", "market") == "limit":
            req = LimitOrderRequest(
                symbol=order_plan["symbol"], qty=order_plan["qty"], side=side,
                time_in_force=tif, limit_price=order_plan["limit_price"])
        else:
            req = MarketOrderRequest(
                symbol=order_plan["symbol"], qty=order_plan["qty"], side=side,
                time_in_force=tif)
        order = self._trading.submit_order(req)
        return str(order.id)

    def cancel(self, order_id: str) -> None:
        self._trading.cancel_order_by_id(order_id)

    def positions(self) -> list[dict]:
        return [
            dict(symbol=p.symbol, qty=float(p.qty), market_value=float(p.market_value))
            for p in self._trading.get_all_positions()
        ]

    def account(self) -> dict:
        a = self._trading.get_account()
        return dict(
            status=str(a.status), buying_power=float(a.buying_power),
            portfolio_value=float(a.portfolio_value), cash=float(a.cash),
            currency=a.currency)

    def fills(self, since: Optional[str] = None) -> list[dict]:
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100)
        out = []
        for o in self._trading.get_orders(req):
            if o.filled_at is None:
                continue
            if since and o.filled_at.isoformat() < since:
                continue
            out.append(self._order_dict(o))
        return out

    def get_order(self, order_id: str) -> dict:
        return self._order_dict(self._trading.get_order_by_id(order_id))

    def simulate_fill(self, order: dict, market_state: dict) -> float:
        latest = float(market_state["price"])
        adj = latest * _HALF_SPREAD_BPS / 1e4
        return latest + adj if order["side"] == "buy" else latest - adj

    def is_market_open(self) -> bool:
        return bool(self._trading.get_clock().is_open)

    def clock(self) -> dict:
        c = self._trading.get_clock()
        return dict(is_open=bool(c.is_open), next_open=str(c.next_open),
                    next_close=str(c.next_close))

    @staticmethod
    def _order_dict(o: Any) -> dict:
        return dict(
            order_id=str(o.id), status=str(o.status),
            filled_qty=float(o.filled_qty) if o.filled_qty is not None else 0.0,
            filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None)
