"""Sharadar SFA bundle entitlement verification (read-only).

Per api-data-sources.md §4 (PURCHASED status):
  Bundle: Sharadar Core US Equities Bundle (SFA)
  Datasets: SF1 (fundamentals), SEP (equity prices), ACTIONS, TICKERS, SP500

Checks:
  1. SHARADAR/TICKERS  — metadata pull (1 row for AAPL)
  2. SHARADAR/SF1      — fundamentals pull (1 row for AAPL)
  3. SHARADAR/SEP      — equity prices (5 rows for AAPL)
  4. SHARADAR/ACTIONS  — corporate actions (5 rows for AAPL)
  5. SHARADAR/SP500    — SP500 constituent history (1 recent row)

Per user instruction: if any dataset is NOT in entitlement, print a clear BLOCKED
message and exit with code 1 — do NOT proceed with integration.

Required env var (never hard-coded, per configuration.md §10):
    NASDAQ_DATA_LINK_API_KEY
"""

import os
import sys

from dotenv import load_dotenv


def check(label: str, fn) -> bool:
    """Run check fn(); return True on success, False on access/auth errors."""
    try:
        result = fn()
        if hasattr(result, "__len__"):
            n = len(result)
        elif hasattr(result, "shape"):
            n = result.shape[0]
        else:
            n = "?"
        print(f"  OK  {label} ({n} rows)")
        return True
    except Exception as e:
        msg = str(e)
        # Distinguish access errors from network/parse errors
        if any(k in msg.lower() for k in ("403", "forbidden", "not found", "unauthorized",
                                           "subscription", "entitlement", "access")):
            print(f"  BLOCKED  {label}: {msg}")
        else:
            print(f"  ERROR  {label}: {msg}")
        return False


def main() -> int:
    load_dotenv()

    api_key = os.environ.get("NASDAQ_DATA_LINK_API_KEY")
    if not api_key:
        print(
            "ERROR: NASDAQ_DATA_LINK_API_KEY not set. "
            "Set it in .env or environment (configuration.md §10 — never hard-code).",
            file=sys.stderr,
        )
        return 1

    try:
        import nasdaqdatalink as ndl
    except ImportError as e:
        print(f"ERROR: nasdaq-data-link not installed: {e}", file=sys.stderr)
        return 1

    ndl.ApiConfig.api_key = api_key

    print("Verifying Sharadar SFA bundle entitlements...")
    print(f"  API key: {'*' * 8}{api_key[-4:]} (last 4 chars)")
    print()

    results: dict[str, bool] = {}

    # 1. TICKERS — metadata
    results["SHARADAR/TICKERS"] = check(
        "SHARADAR/TICKERS (AAPL metadata)",
        lambda: ndl.get_table("SHARADAR/TICKERS", ticker="AAPL"),
    )

    # 2. SF1 — fundamentals (as-reported quarterly, 1 row)
    results["SHARADAR/SF1"] = check(
        "SHARADAR/SF1 (AAPL ARQ fundamentals)",
        lambda: ndl.get_table(
            "SHARADAR/SF1",
            ticker="AAPL",
            dimension="ARQ",
            paginate=True,
        ).head(1),
    )

    # 3. SEP — equity prices (survivorship-free daily bars)
    results["SHARADAR/SEP"] = check(
        "SHARADAR/SEP (AAPL daily prices)",
        lambda: ndl.get_table(
            "SHARADAR/SEP",
            ticker="AAPL",
            paginate=True,
        ).head(5),
    )

    # 4. ACTIONS — corporate actions
    results["SHARADAR/ACTIONS"] = check(
        "SHARADAR/ACTIONS (AAPL actions)",
        lambda: ndl.get_table(
            "SHARADAR/ACTIONS",
            ticker="AAPL",
            paginate=True,
        ).head(5),
    )

    # 5. SP500 — constituent history (the one we need for PIT universe service)
    results["SHARADAR/SP500"] = check(
        "SHARADAR/SP500 (constituent history)",
        lambda: ndl.get_table(
            "SHARADAR/SP500",
            paginate=True,
        ).head(1),
    )

    print()
    all_ok = all(results.values())
    blocked = [k for k, v in results.items() if not v]

    if all_ok:
        print("SUCCESS: All 5 Sharadar SFA datasets are accessible.")
        print("  Integration may proceed per api-data-sources.md §4.")
        return 0
    else:
        print("BLOCKED: The following datasets are NOT accessible:")
        for dataset in blocked:
            print(f"  - {dataset}")
        print()
        print("Do NOT proceed with integration for blocked datasets.")
        print("Contact Nasdaq Data Link support or check subscription at data.nasdaq.com.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
