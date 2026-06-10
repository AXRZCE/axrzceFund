"""G0.5 broker round-trip drill — validation-criteria.md G0.5.

10 scripted paper orders: submit -> fill -> reconcile with zero mismatches;
modeled-fill logging populated on all 10.

Script: BUY 1 share of each of 5 liquid names (market orders), wait for fills,
then SELL 1 share of each — 10 orders total, flat at the end. For every order we
log BOTH the broker-reported fill and our modeled fill (latest trade price plus a
1bp half-spread floor per backtesting-framework.md §3.3 — megacap floor; the
divergence becomes the standing fill-divergence metric of api-data-sources §2.1).

Reconciliation (all must hold for every order):
  - terminal status == FILLED, filled_qty == requested qty
  - broker fill price present and positive
  - modeled fill logged
  - net position change across the buy/sell pair == 0 (account flat afterwards)

Market-hours guard: paper market orders only fill while the market is open. If
closed, exits with code 2 and the next open time - run it during market hours.

Read/write scope: paper account only (paper-api.alpaca.markets), 5 long shares
held for ~seconds. No real money exists anywhere in this system.

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

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
HALF_SPREAD_BPS = 1.0           # megacap floor, backtesting-framework.md §3.3
FILL_TIMEOUT_S = 120
ARTIFACT_DIR = Path("var/g05")


def modeled_fill(latest_trade: float, side: str) -> float:
    adj = latest_trade * HALF_SPREAD_BPS / 1e4
    return latest_trade + adj if side == "buy" else latest_trade - adj


def main() -> int:
    load_dotenv()
    import os
    key, secret = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        print("ERROR: Alpaca keys not set", file=sys.stderr)
        return 1

    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    trading = TradingClient(api_key=key, secret_key=secret, paper=True)
    data = StockHistoricalDataClient(api_key=key, secret_key=secret)

    clock = trading.get_clock()
    if not clock.is_open:
        print(f"Market closed. Next open: {clock.next_open}. Run during market hours.")
        return 2

    run_id = f"g05_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:6]}"
    event_log = EventLog()
    records = []

    def place(side: str) -> None:
        for sym in SYMBOLS:
            latest = data.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=sym, feed="iex"))[sym]
            model = modeled_fill(float(latest.price), side)
            order = trading.submit_order(MarketOrderRequest(
                symbol=sym, qty=1,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY))
            records.append({
                "symbol": sym, "side": side, "order_id": str(order.id),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "latest_trade_at_submit": float(latest.price),
                "modeled_fill": model,
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
                o = trading.get_order_by_id(r["order_id"])
                if str(o.status).lower().endswith("filled") and o.filled_avg_price:
                    r["broker_fill"] = float(o.filled_avg_price)
                    r["filled_qty"] = float(o.filled_qty)
                    r["status"] = str(o.status)
                    r["divergence_bps"] = (
                        (r["broker_fill"] - r["modeled_fill"]) / r["modeled_fill"] * 1e4
                    )
                    pending.discard(r["order_id"])
                    print(f"  filled    {r['side'].upper():4} 1 {r['symbol']}  "
                          f"broker={r['broker_fill']:.4f}  div={r['divergence_bps']:+.1f}bps")
        return not pending

    print(f"=== G0.5 BROKER ROUND-TRIP {run_id} ===")
    pos_before = {p.symbol: float(p.qty) for p in trading.get_all_positions()}

    place("buy")
    if not await_fills():
        print("ERROR: buy fills timed out")
        return 1
    place("sell")
    if not await_fills():
        print("ERROR: sell fills timed out")
        return 1

    pos_after = {p.symbol: float(p.qty) for p in trading.get_all_positions()}

    # Reconciliation
    mismatches = []
    for r in records:
        if r.get("status", "").lower() != "orderstatus.filled" and "filled" not in r.get("status", "").lower():
            mismatches.append(f"{r['order_id']}: status {r.get('status')}")
        if r.get("filled_qty") != 1.0:
            mismatches.append(f"{r['order_id']}: filled_qty {r.get('filled_qty')}")
        if not r.get("broker_fill", 0) > 0:
            mismatches.append(f"{r['order_id']}: no broker fill price")
        if "modeled_fill" not in r:
            mismatches.append(f"{r['order_id']}: modeled fill missing")
    for sym in SYMBOLS:
        if pos_before.get(sym, 0.0) != pos_after.get(sym, 0.0):
            mismatches.append(f"{sym}: position changed {pos_before.get(sym,0)} -> {pos_after.get(sym,0)}")

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
