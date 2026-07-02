#!/usr/bin/env python
"""The week-close / daily audit (WP6 R5/R6) — runs OFF-VM from the pulled repo alone.

Recomputes a session's five clean-week criteria FROM THE COMMITTED ARTIFACTS (never trusts a
flag): (1) wall attestation present; (2) replay-determinism — the hash is RECOMPUTED here from the
artifact's decision payloads and compared to the in-run hash; (3) the artifact exists in the repo
(= Track A committed it); (4) spend within the daily cap; (5) monitor ticks recorded. Also derives
calendar gaps (R6) and classifies market_closed (R9) and cycle_failed (R7 — a fail-closed day is a
counted OBSERVATION).

Usage: python ops/audit_week.py 2026-07-06 [2026-07-10]
Exit 0 = every expected session accounted for and clean/observed; nonzero otherwise.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

from core.budget import DAILY_CAP_USD
from graphs.daily_cycle import is_trading_session, replay_hash

ART_DIR = Path("results/wp6")


def audit_session(date_iso: str) -> dict:
    """The five criteria for one session, from the artifact alone."""
    path = ART_DIR / f"cycle_{date_iso.replace('-', '')}.json"
    if not path.exists():
        if not is_trading_session(date_iso):
            return {"date": date_iso, "class": "non_session", "ok": True}
        return {"date": date_iso, "class": "MISSED", "ok": False,
                "detail": "trading session with no committed artifact (R6: recorded as a gap, "
                          "never backfilled)"}
    a = json.loads(path.read_text())
    status = a.get("status")
    if status == "market_closed":
        return {"date": date_iso, "class": "market_closed", "ok": True}
    if status == "cycle_failed":
        return {"date": date_iso, "class": "fail_closed_observation", "ok": True,
                "detail": a.get("detail", "")}  # R7: fail-CLOSED counts as an observation

    checks = {
        "wall_attested": (a.get("wall_attestation", {}).get("wall") == "attested"
                          and a["wall_attestation"].get("broker_write_calls") == 0),
        "replay_determinism": (
            replay_hash(a.get("replay_check", {}).get("payloads", []))
            == a.get("replay_check", {}).get("hash")),
        "artifact_committed": True,  # we are reading it from the pulled repo
        "spend_within_cap": (a.get("spend", {}).get("day_spent_usd", 1e9) < DAILY_CAP_USD
                             or a.get("spend", {}).get("stopped") is True),
        "monitor_ticks_recorded": "monitor" in a and "breaker_state" in a.get("monitor", {}),
    }
    return {"date": date_iso, "class": "session", "ok": all(checks.values()),
            "checks": checks,
            "spend_usd": a.get("spend", {}).get("day_spent_usd"),
            "decisions": len(a.get("decisions", []))}


def audit_range(start_iso: str, end_iso: str) -> dict:
    d0, d1 = _dt.date.fromisoformat(start_iso), _dt.date.fromisoformat(end_iso)
    days = []
    d = d0
    while d <= d1:
        days.append(audit_session(d.isoformat()))
        d += _dt.timedelta(days=1)
    sessions = [x for x in days if x["class"] in ("session", "fail_closed_observation")]
    missed = [x for x in days if x["class"] == "MISSED"]
    # integrity failures = SESSION days failing a criterion (misses are governed by the R6
    # miss-count rule, not the integrity rule — 1 miss extends, it does not dirty the week)
    integrity = [x for x in days if x["class"] == "session" and not x["ok"]]
    return {"days": days,
            "sessions_counted": len(sessions),
            "missed": [x["date"] for x in missed],
            "integrity_failures": [x["date"] for x in integrity],
            "week_ok": not integrity and len(missed) <= 1,  # R6: one miss extends, doesn't reset
            "note": "R6: 1 miss extends the week by one session; 2+ misses or any integrity "
                    "failure resets."}


def main(argv: list[str]) -> int:
    start = argv[1]
    end = argv[2] if len(argv) > 2 else start
    report = audit_range(start, end)
    print(json.dumps(report, indent=2))
    return 0 if report["week_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
