"""Alpaca paper-trading verification (read-only), via the R5 adapters.

Per api-data-sources.md §2.1: Paper-Only accounts get IEX data. No vendor SDK is
imported here — account + bars come through data/interfaces. Read-only: no orders.

Usage:  python ops/verify_alpaca.py
"""
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    try:
        from data.interfaces import AlpacaBroker, AlpacaMarketData
    except ImportError as e:
        print(f"ERROR: adapters unavailable: {e}", file=sys.stderr)
        return 1
    try:
        broker = AlpacaBroker(paper=True)
        market = AlpacaMarketData()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("Connecting to Alpaca paper trading (via adapter)...")
    try:
        acct = broker.account()
    except Exception as e:
        print(f"ERROR fetching account: {e}", file=sys.stderr)
        return 1

    print("\n-- Account --")
    print(f"  Status       : {acct['status']}")
    print(f"  Buying power : ${acct['buying_power']:,.2f}")
    print(f"  NAV          : ${acct['portfolio_value']:,.2f}")
    print(f"  Cash         : ${acct['cash']:,.2f}")
    print(f"  Currency     : {acct['currency']}")
    if "ACTIVE" not in acct["status"].upper():
        print(f"\nWARNING: Account status is '{acct['status']}' — expected ACTIVE.", file=sys.stderr)

    print("\nFetching AAPL daily bars (IEX feed, via adapter)...")
    try:
        df = market.get_daily_bars(["AAPL"], window_days=14)
    except Exception as e:
        print(f"ERROR fetching bars: {e}", file=sys.stderr)
        return 1

    print("\n-- AAPL last 5 daily bars (IEX) --")
    print(f"  {'Date':<12} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>12}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")
    for r in df.tail(5).itertuples():
        date_str = str(r.timestamp)[:10]
        print(f"  {date_str:<12} {r.open:>8.2f} {r.high:>8.2f} {r.low:>8.2f} "
              f"{r.close:>8.2f} {int(r.volume):>12,}")

    print(f"\n  Bars returned : {len(df)}")
    print("  Feed          : IEX (paper-only, ~2.5% of consolidated volume)")
    print("\nSUCCESS: Alpaca paper account verified through the adapter (read-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
