"""Sharadar SFA bundle entitlement verification (read-only), via the R5 adapter.

Per api-data-sources.md §4: SF1, SEP, ACTIONS, TICKERS, SP500. No vendor SDK is
imported here — all pulls go through data/interfaces.SharadarData. If any dataset
is not in our entitlement the check prints BLOCKED and exits 1.

Usage:  python ops/verify_sharadar.py
"""
import sys

from dotenv import load_dotenv


def check(label: str, fn) -> bool:
    try:
        result = fn()
        n = result.shape[0] if hasattr(result, "shape") else len(result)
        print(f"  OK  {label} ({n} rows)")
        return True
    except Exception as e:
        msg = str(e)
        if any(k in msg.lower() for k in ("403", "forbidden", "not found", "unauthorized",
                                          "subscription", "entitlement", "access")):
            print(f"  BLOCKED  {label}: {msg}")
        else:
            print(f"  ERROR  {label}: {msg}")
        return False


def main() -> int:
    load_dotenv()
    try:
        from data.interfaces import SharadarData
    except ImportError as e:
        print(f"ERROR: adapter unavailable: {e}", file=sys.stderr)
        return 1
    try:
        sh = SharadarData()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("Verifying Sharadar SFA bundle entitlements (via adapter)...\n")
    results = {
        "SHARADAR/TICKERS": check("SHARADAR/TICKERS (AAPL metadata)", lambda: sh.ping("AAPL")),
        "SHARADAR/SF1": check("SHARADAR/SF1 (fundamentals delta)",
                              lambda: sh.get_fundamentals(window_days=60).head(1)),
        "SHARADAR/SEP": check("SHARADAR/SEP (daily prices)",
                              lambda: sh.get_daily_bars(window_days=7).head(5)),
        "SHARADAR/ACTIONS": check("SHARADAR/ACTIONS (corporate actions)",
                                  lambda: sh.get_corporate_actions(window_days=90).head(5)),
        "SHARADAR/SP500": check("SHARADAR/SP500 (constituent history)",
                                lambda: sh.get_index_constituents("SP500").head(1)),
    }

    print()
    blocked = [k for k, v in results.items() if not v]
    if not blocked:
        print("SUCCESS: All 5 Sharadar SFA datasets are accessible through the adapter.")
        return 0
    print("BLOCKED: the following datasets are NOT accessible:")
    for d in blocked:
        print(f"  - {d}")
    print("\nDo NOT proceed with integration for blocked datasets.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
