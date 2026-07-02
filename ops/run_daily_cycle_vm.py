#!/usr/bin/env python
"""VM entrypoint for the WP6 daily cycle — what hedgefund-cycle.service execs.

Usage: python ops/run_daily_cycle_vm.py [YYYY-MM-DD]   (default: today in America/New_York)

Computes the prior-week spend from the committed results/wp6/ artifacts (the R8 week cap is
enforced against the WHOLE week), wires the real client/manifest/market-data, and runs
graphs.daily_cycle.run_daily_cycle. Exit 0 even on a fail-closed day — the RECORD is the outcome
(R7); a nonzero exit is reserved for the entrypoint itself breaking (watchdog-visible).
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(".env")

from core.event_log import EventLog  # noqa: E402
from core.llm import OpenRouterClient  # noqa: E402
from core.manifest import load_manifest  # noqa: E402
from graphs.daily_cycle import run_daily_cycle  # noqa: E402

WEEK_START = "2026-07-06"  # the ruled clean week (R5); prior-week spend sums from here


def _prior_week_spend() -> float:
    total = 0.0
    for f in glob.glob("results/wp6/cycle_*.json"):
        try:
            a = json.loads(Path(f).read_text())
            if a.get("session_date", "") >= WEEK_START:
                total += float(a.get("spend", {}).get("day_spent_usd", 0.0))
        except Exception:
            continue
    return round(total, 6)


def main() -> int:
    session_date = (sys.argv[1] if len(sys.argv) > 1
                    else _dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    try:
        market_data = None
        try:
            from data.interfaces.alpaca import AlpacaMarketData
            market_data = AlpacaMarketData()  # read-only quotes (R2); absent keys → gaps recorded
        except Exception:
            pass
        summary = run_daily_cycle(
            session_date=session_date,
            client=OpenRouterClient(),
            manifest=load_manifest(),
            event_log=EventLog(Path("var/wp6_event_log.db")),
            market_data=market_data,
            prior_week_spend_usd=_prior_week_spend(),
        )
        print(json.dumps({"session_date": session_date, "status": summary.get("status"),
                          "spend": summary.get("spend", {}).get("day_spent_usd", 0.0)}))
        return 0  # fail-closed days are recorded observations (R7)
    except Exception as e:  # the entrypoint itself broke — watchdog-visible
        print(f"ENTRYPOINT FAILURE: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
