#!/usr/bin/env python
"""WP6-CP2 step 1 ($0): the TECH-01 252-day SEP backfill for the screened names + a fresh
universe scan, run ON THE VM store. Commits (via Track A) results/wp6/universe_scan.json —
names, ranks, floors applied, and the R4 waiver log line.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(".env")

from data.ingestion import ingest_sep  # noqa: E402
from data.pit_store import PITStore  # noqa: E402
from graphs.screen import scan_universe, screen_candidates  # noqa: E402


def main() -> None:
    store = PITStore()
    ts = _dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")

    rows = scan_universe()
    pre = screen_candidates(rows, held=[])
    targets = sorted(set(pre.new_candidates) | set(pre.held_candidates))
    print(f"pre-scan: new={pre.new_candidates} held={pre.held_candidates} -> backfill {targets}")

    job = ingest_sep(store, run_id=f"wp6_backfill_{ts}", window_days=380, tickers=targets)
    print("backfill job:", job)

    rows2 = scan_universe()
    post = screen_candidates(rows2, held=[])
    ranked_top = sorted((r for r in rows2 if r.ticker in set(post.new_candidates)),
                        key=lambda r: -r.adv_usd_20d)
    artifact = {
        "scanned_at": ts,
        "backfill": {"targets": targets, "window_days": 380,
                     "job": {"status": job.status, "rows": job.rows, "error": job.error}},
        "screen": {
            "new_candidates": post.new_candidates,
            "held": post.held_candidates,
            "ranks": [{"ticker": r.ticker, "adv_usd_20d": round(r.adv_usd_20d, 2),
                       "last_close": r.last_close} for r in ranked_top],
            "floors": "SP500-PIT ∩ fundamentals>=6 ∩ ADV>=$20M ∩ price>=$5",
            "excluded_count": len(post.excluded),
            "waiver": post.waiver_note,
        },
    }
    out = Path("results/wp6")
    out.mkdir(parents=True, exist_ok=True)
    (out / "universe_scan.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps(artifact["screen"], indent=2))


if __name__ == "__main__":
    main()
