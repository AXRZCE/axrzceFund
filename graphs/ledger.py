"""Week-accumulating book ledger + breaker persistence + pending-order settlement (WP6 CP1).

Everything here is EVENT-LOG-DERIVED (the pmort_pending pattern — restart-proof by construction;
memory-systems §1: the log is the source of truth, every view rebuilds from it):

  - **Book:** replayed from `modeled_order` / `order_settled` events + the latest `mark_to_market`
    event. Positions feed the gate's sector/gross/net checks (`risk_gate.Position`) and the
    monitor's NAV. Phase-1 modeled NAV = starting NAV + Σ unrealized PnL on modeled fills
    (no financing/fees — the cost model prices the EDGE bar, not the book).
  - **Settlement:** a `pending_next_open` order (decided post-close on day D) is settled at day
    D+1's actual open via the WP0 half-spread convention — an `order_settled` event. Never settled
    without a real open bar (no bar ⇒ stays pending, gap recorded).
  - **Breaker state:** persisted as `breaker_snapshot` events each cycle; restored via
    `BreakerStateMachine.from_snapshot` — HALT persists across restarts (P12: only a human moves
    it), red-tested.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from core.config import param_number
from graphs.monitor import BreakerStateMachine
from graphs.risk_gate import Position

logger = structlog.get_logger()

STARTING_NAV_USD = 1_000_000.0  # configuration.md §1 starting_paper_nav ($1,000,000 defeats the
                                # numeric parser — the literal is guard-tested in tests/test_ledger.py)
HALF_SPREAD_BPS = param_number("cost_half_spread_bps")


def config_doc_carries_starting_nav() -> bool:
    from pathlib import Path
    return "`starting_paper_nav = $1,000,000`" in Path("docs/configuration.md").read_text(encoding="utf-8")


def replay_book(event_log: Any) -> dict:
    """Rebuild the modeled book from the log. Returns {positions: [Position], nav_usd, holdings:
    {ticker: {signed_qty, fill_price, sector, mark}}, pending: [order dicts]}."""
    holdings: dict[str, dict] = {}
    pending: list[dict] = []
    settled_ids: set[str] = set()
    marks: dict[str, float] = {}

    for e in event_log.get_events():
        if e.event_type == "order_settled":
            settled_ids.add(e.payload["pending_ref"])
    for e in event_log.get_events():
        if e.event_type == "modeled_order":
            o = e.payload["order"]
            ref = e.payload["replay_tuple"]["trade_id"]
            if o["status"] == "pending_next_open" and ref not in settled_ids:
                pending.append({**o, "pending_ref": ref, "sector": e.payload.get("sector", "?")})
            elif o["status"] == "modeled_filled":
                _apply_fill(holdings, o, e.payload.get("sector", "?"))
        elif e.event_type == "order_settled":
            _apply_fill(holdings, e.payload["order"], e.payload.get("sector", "?"))
        elif e.event_type == "mark_to_market":
            marks.update(e.payload["marks"])

    positions: list[Position] = []
    nav = STARTING_NAV_USD
    for t, h in sorted(holdings.items()):
        if h["signed_qty"] == 0:
            continue
        mark = marks.get(t, h["fill_price"])
        h["mark"] = mark
        nav += h["signed_qty"] * (mark - h["fill_price"])
        positions.append(Position(ticker=t, sector=h["sector"],
                                  signed_notional_usd=h["signed_qty"] * mark))
    return {"positions": positions, "nav_usd": round(nav, 2), "holdings": holdings,
            "pending": pending}


def _apply_fill(holdings: dict, order: dict, sector: str) -> None:
    sign = 1 if order["side"] == "buy" else -1
    qty = sign * int(order["qty"])
    fill = float(order["modeled_fill_price"])
    h = holdings.setdefault(order["symbol"], {"signed_qty": 0, "fill_price": 0.0, "sector": sector})
    prev_qty = h["signed_qty"]
    new_qty = prev_qty + qty
    if new_qty != 0 and prev_qty != 0 and (prev_qty > 0) == (new_qty > 0):
        # add: weighted-average entry (Phase-1 simple)
        h["fill_price"] = (abs(prev_qty) * h["fill_price"] + abs(qty) * fill) / abs(new_qty)
    elif prev_qty == 0:
        h["fill_price"] = fill
    h["signed_qty"] = new_qty
    h["sector"] = sector


def settle_pending(event_log: Any, opens: dict[str, float], *, cycle_id: str) -> list[dict]:
    """Settle day-D pending orders at day-D+1's REAL open (no bar ⇒ stays pending, gap recorded).
    Emits `order_settled` events; returns the settlements."""
    book = replay_book(event_log)
    settled = []
    for p in book["pending"]:
        open_px = opens.get(p["symbol"])
        if open_px is None:
            event_log.append(event_type="settlement_gap", cycle_id=cycle_id, agent_id="LEDGER",
                             payload={"pending_ref": p["pending_ref"], "symbol": p["symbol"],
                                      "reason": "no open bar — stays pending, never interpolated"})
            continue
        adj = open_px * HALF_SPREAD_BPS / 1e4
        fill = open_px + adj if p["side"] == "buy" else open_px - adj
        order = {**{k: p[k] for k in ("symbol", "side", "qty", "order_type", "tif",
                                      "limit_price", "notional_usd")},
                 "status": "modeled_filled", "modeled_fill_price": round(fill, 6),
                 "full_fill": True}
        event_log.append(event_type="order_settled", cycle_id=cycle_id, agent_id="LEDGER",
                         payload={"order": order, "pending_ref": p["pending_ref"],
                                  "sector": p.get("sector", "?"), "open_price": open_px})
        settled.append(order)
        logger.info("order_settled", symbol=p["symbol"], open=open_px, fill=fill)
    return settled


def record_marks(event_log: Any, marks: dict[str, float], *, cycle_id: str) -> None:
    event_log.append(event_type="mark_to_market", cycle_id=cycle_id, agent_id="LEDGER",
                     payload={"marks": marks})


def persist_breakers(event_log: Any, machine: BreakerStateMachine, *, cycle_id: str) -> None:
    event_log.append(event_type="breaker_snapshot", cycle_id=cycle_id, agent_id="MONITOR",
                     payload={"snapshot": machine.snapshot()})


def restore_breakers(event_log: Any) -> BreakerStateMachine:
    """Latest snapshot wins; no snapshot ⇒ a fresh machine at starting NAV. HALT persists (P12)."""
    snap: Optional[dict] = None
    for e in event_log.get_events(agent_id="MONITOR"):
        if e.event_type == "breaker_snapshot":
            snap = e.payload["snapshot"]
    return BreakerStateMachine.from_snapshot(snap) if snap else BreakerStateMachine(STARTING_NAV_USD)
