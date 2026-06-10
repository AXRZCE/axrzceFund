"""Alpaca paper-trading hello-world verification (read-only).

Per api-data-sources.md §2.1:
- Paper-Only accounts connect to paper-api.alpaca.markets.
- Free data feed is IEX-only (~2.5% of consolidated volume) — adequate for daily cadence.
- Read-only: no orders submitted here.

Usage:
    python ops/verify_alpaca.py

Required environment variables (never hard-coded, per configuration.md §10):
    APCA_API_KEY_ID     — Alpaca paper account API key
    APCA_API_SECRET_KEY — Alpaca paper account API secret
"""

import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv


def main() -> int:
    # Load .env file if present (development convenience; prod uses real env vars)
    load_dotenv()

    api_key = os.environ.get("APCA_API_KEY_ID")
    api_secret = os.environ.get("APCA_API_SECRET_KEY")

    if not api_key or not api_secret:
        print(
            "ERROR: APCA_API_KEY_ID and APCA_API_SECRET_KEY must be set in environment "
            "or .env file. See api-data-sources.md §2.1.",
            file=sys.stderr,
        )
        return 1

    # Import here so module is usable even if alpaca-py isn't installed
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError as e:
        print(f"ERROR: alpaca-py not installed: {e}", file=sys.stderr)
        return 1

    # ── 1. Trading client (paper) ──────────────────────────────────────────
    print("Connecting to Alpaca paper trading...")
    try:
        trading_client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=True,
        )
        account = trading_client.get_account()
    except Exception as e:
        print(f"ERROR fetching account: {e}", file=sys.stderr)
        return 1

    print("\n-- Account --")
    print(f"  Status       : {account.status}")
    print(f"  Buying power : ${float(account.buying_power):,.2f}")
    print(f"  NAV          : ${float(account.portfolio_value):,.2f}")
    print(f"  Cash         : ${float(account.cash):,.2f}")
    print(f"  Currency     : {account.currency}")

    if str(account.status) not in ("ACTIVE", "AccountStatus.ACTIVE"):
        print(f"\nWARNING: Account status is '{account.status}' — expected ACTIVE.", file=sys.stderr)

    # ── 2. Market data client (IEX feed) ───────────────────────────────────
    print("\nFetching AAPL daily bars (IEX feed, last 5 trading days)...")
    try:
        data_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
        )

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=14)  # 14 calendar days to ensure ≥5 trading days

        request = StockBarsRequest(
            symbol_or_symbols=["AAPL"],
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed="iex",  # Explicitly IEX — free feed per api-data-sources.md §3
            limit=5,
        )
        bars_response = data_client.get_stock_bars(request)
        bars = bars_response["AAPL"]
    except Exception as e:
        print(f"ERROR fetching bars: {e}", file=sys.stderr)
        return 1

    print("\n-- AAPL last 5 daily bars (IEX) --")
    print(f"  {'Date':<12} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>12}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")
    for bar in bars[-5:]:
        date_str = bar.timestamp.strftime("%Y-%m-%d")
        print(
            f"  {date_str:<12} "
            f"{float(bar.open):>8.2f} "
            f"{float(bar.high):>8.2f} "
            f"{float(bar.low):>8.2f} "
            f"{float(bar.close):>8.2f} "
            f"{int(bar.volume):>12,}"
        )

    print(f"\n  Bars returned : {len(bars)}")
    print(f"  Feed          : IEX (paper-only, ~2.5% of consolidated volume)")

    print("\nSUCCESS: Alpaca paper account verified.")
    print("  No orders were submitted. Read-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
