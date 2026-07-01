"""Nightly ingestion runner — G0.3 soak driver.

Runs all five ingestion jobs, reconciles row counts against the previous night,
persists a JSON summary per night to results/soak/ (tracked — the VM commits it), and prints an ASCII
report. G0.3 = 5 consecutive nights, zero unexplained row-count deviations.

Scheduled via systemd on the VM (deploy/systemd/hedgefund-soak.*). Manual run:
    python ops/nightly_ingest.py
"""
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

from core.event_log import EventLog
from data.ingestion import run_nightly
from data.pit_store import PITStore

LOG_DIR = Path("results/soak")  # tracked: our G0.3 stats (row counts/flags), committed off-box

# Reconciliation tolerance: fractional deviation vs the previous night above which
# a job's row count is flagged for explanation (vendor revision, holiday, etc.).
DEVIATION_TOLERANCE = 0.5


def reconcile(summary: dict, prev: dict | None) -> list[str]:
    """Compare tonight's per-job row counts with the previous night's."""
    flags = []
    if not prev:
        flags.append("baseline night - no previous run to reconcile against")
        return flags
    prev_rows = {j["job"]: j["rows"] for j in prev.get("jobs", [])}
    for j in summary["jobs"]:
        p = prev_rows.get(j["job"])
        if p is None:
            flags.append(f"{j['job']}: new job, no baseline")
            continue
        if p == 0 and j["rows"] == 0:
            continue
        base = max(p, 1)
        dev = abs(j["rows"] - p) / base
        if dev > DEVIATION_TOLERANCE:
            flags.append(
                f"{j['job']}: rows {p} -> {j['rows']} ({dev:+.0%} deviation) - EXPLAIN OR INVESTIGATE"
            )
    return flags


def main() -> int:
    load_dotenv()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    run_id = f"ingest_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:6]}"
    store = PITStore()
    event_log = EventLog()

    summary = run_nightly(store, event_log, run_id)

    # Reconcile vs previous night
    prior = sorted(LOG_DIR.glob("night_*.json"))
    prev = json.loads(prior[-1].read_text(encoding="utf-8")) if prior else None
    flags = reconcile(summary, prev)
    summary["reconciliation_flags"] = flags

    out = LOG_DIR / f"night_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"\n=== NIGHTLY INGESTION {run_id} ===")
    for j in summary["jobs"]:
        mark = "OK " if j["status"] == "ok" else "ERR"
        print(f"  [{mark}] {j['job']:<22} rows={j['rows']:<8} source={j['source']}"
              + (f"  error={j['error']}" if j.get("error") else ""))
    print(f"  PIT audit violations: {len(summary['pit_audit_violations'])}")
    for f in flags:
        print(f"  RECON: {f}")
    print(f"  summary: {out}")
    print(f"  ALL OK: {summary['all_ok']}")

    store.close()
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
