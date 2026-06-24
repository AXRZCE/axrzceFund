"""G0.5 broker round-trip drill — validation-criteria.md G0.5.

10 scripted paper orders: submit -> fill -> reconcile with zero mismatches;
modeled-fill logging populated on all 10. BUY 1 share of 5 liquid names, wait for
fills, then SELL 1 of each — flat at the end.

All broker/market-data access goes through the R5 adapters (data/interfaces) — no
vendor SDK is imported here.

Market-hours guard: paper market orders only fill while the market is open; exits 2
(with the next open time) if closed. Read/write scope: paper account only.

Usage:  python ops/broker_roundtrip.py
"""
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

from core.event_log import EventLog
from data.interfaces import AlpacaBroker, AlpacaMarketData

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
FILL_TIMEOUT_S = 120
ARTIFACT_DIR = Path("var/g05")


def main() -> int:
    load_dotenv()
    try:
        broker = AlpacaBroker(paper=True)
        market = AlpacaMarketData()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    clock = broker.clock()
    if not clock["is_open"]:
        print(f"Market closed. Next open: {clock['next_open']}. Run during market hours.")
        return 2

    run_id = f"g05_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:6]}"
    event_log = EventLog()
    records = []

    def place(side: str) -> None:
        for sym in SYMBOLS:
            latest = market.get_latest_trade(sym)
            model = broker.simulate_fill({"side": side}, {"price": latest})
            order_id = broker.submit(
                {"symbol": sym, "qty": 1, "side": side, "type": "market", "tif": "day"})
            records.append({
                "symbol": sym, "side": side, "order_id": order_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "latest_trade_at_submit": latest, "modeled_fill": model,
            })
            print(f"  submitted {side.upper():4} 1 {sym}  modeled={model:.4f}")

    def await_fills() -> bool:
        deadline = time.time() + FILL_TIMEOUT_S
        pending = {r["order_id"] for r in records if "broker_fill" not in r}
        while pending and time.time() < deadline:
            time.sleep(2)
            for r in records:
                if r["order_id"] not in pending:
                    continue
                o = broker.get_order(r["order_id"])
                if o["status"].lower().endswith("filled") and o["filled_avg_price"]:
                    r["broker_fill"] = o["filled_avg_price"]
                    r["filled_qty"] = o["filled_qty"]
                    r["status"] = o["status"]
                    r["divergence_bps"] = (
                        (r["broker_fill"] - r["modeled_fill"]) / r["modeled_fill"] * 1e4)
                    pending.discard(r["order_id"])
                    print(f"  filled    {r['side'].upper():4} 1 {r['symbol']}  "
                          f"broker={r['broker_fill']:.4f}  div={r['divergence_bps']:+.1f}bps")
        return not pending

    print(f"=== G0.5 BROKER ROUND-TRIP {run_id} ===")
    pos_before = {p["symbol"]: p["qty"] for p in broker.positions()}

    place("buy")
    if not await_fills():
        print("ERROR: buy fills timed out")
        return 1
    place("sell")
    if not await_fills():
        print("ERROR: sell fills timed out")
        return 1

    pos_after = {p["symbol"]: p["qty"] for p in broker.positions()}

    mismatches = []
    for r in records:
        if "filled" not in r.get("status", "").lower():
            mismatches.append(f"{r['order_id']}: status {r.get('status')}")
        if r.get("filled_qty") != 1.0:
            mismatches.append(f"{r['order_id']}: filled_qty {r.get('filled_qty')}")
        if not r.get("broker_fill", 0) > 0:
            mismatches.append(f"{r['order_id']}: no broker fill price")
        if "modeled_fill" not in r:
            mismatches.append(f"{r['order_id']}: modeled fill missing")
    for sym in SYMBOLS:
        if pos_before.get(sym, 0.0) != pos_after.get(sym, 0.0):
            mismatches.append(f"{sym}: position changed {pos_before.get(sym, 0)} -> {pos_after.get(sym, 0)}")

    summary = {
        "run_id": run_id, "orders": records, "mismatches": mismatches,
        "n_orders": len(records),
        "modeled_fill_logged_on_all": all("modeled_fill" in r for r in records),
        "pass": len(records) == 10 and not mismatches,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{run_id}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    event_log.append(event_type="broker_roundtrip_drill", cycle_id=run_id, payload=summary)

    print(f"\n  orders={len(records)}  mismatches={len(mismatches)}")
    for m in mismatches:
        print(f"  MISMATCH: {m}")
    print(f"  artifact: {out}")
    print(f"  G0.5 VERDICT: {'PASS' if summary['pass'] else 'FAIL'}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
