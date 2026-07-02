"""Order manager (WP4 R3) + THE WALL (WP4 R2 — the cardinal rule).

Turns a GATE-APPROVED proposal into a **MODELED, LOGGED order — never a submitted one**:

  - qty = floor(NAV × size_pct_nav / price), whole shares (rounding rule pinned by test);
  - side from direction (long→buy, short→sell); order type from the Phase-1 entry vocabulary
    (market_open / limit); TIF day;
  - modeled fill at the cost model's half-spread (`core/costs.HALF_SPREAD_BPS`), the WP0
    `simulate_fill` convention: buy fills up, sell fills down;
  - market CLOSED ⇒ the order is `pending_next_open` with NO modeled fill (a fill modeled off a
    closed market's stale price is a hoax — wp4-done-criteria R7.1);
  - modeled fills are COMPLETE-at-once by Phase-1 ruling (R7.2: at ≤0.005% ADV participation,
    modeling partials would be false precision) — every fill event carries the explicit
    `full_fill: true` marker so WP7's real partial-fill handling has a defined divergence point;
  - every order/fill event is replay-stamped (ReplayTuple incl. `manifest_version`).

**THE WALL (R2):** this module takes NO broker write handle and imports NO broker module — there
is no code path from here to `AlpacaBroker.submit` (AST-scan-enforced by tests/test_orders.py).
The only submission surface is `submit_live`, which UNCONDITIONALLY raises `LiveSubmissionBlocked`.
The Alpaca PAPER API counts as live for WP4 — G0.5 proved the write path works; WP4 proves it is
never reached. Lifting the wall is WP7's own logged, human-reviewed change, not a flag flip.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional

import structlog

from core.config import load_config
from core.costs import HALF_SPREAD_BPS
from core.replay import ReplayTuple, new_trade_id

logger = structlog.get_logger()


class OrderError(Exception):
    """The proposal could not be turned into a valid modeled order (fail-closed)."""


class LiveSubmissionBlocked(Exception):
    """WP4 cardinal rule: orders are modeled/logged, NEVER submitted, until WP7."""


def submit_live(*_args: Any, **_kwargs: Any) -> str:
    """The ONLY submission surface in the WP4 order path — and it always refuses.

    Raises unconditionally. Not gated on a flag: lifting the dry-run wall is WP7's own logged,
    reviewed change (wp4-done-criteria R2), never a config flip.
    """
    raise LiveSubmissionBlocked(
        "WP4: orders are MODELED/LOGGED, never submitted (paper API included). "
        "The wall lifts at WP7 via its own logged, human-reviewed change."
    )


@dataclass(frozen=True)
class ModeledOrder:
    symbol: str
    side: str                    # "buy" | "sell"
    qty: int                     # whole shares, floor-rounded
    order_type: str              # "market_open" | "limit"
    tif: str
    limit_price: Optional[float]
    notional_usd: float
    status: str                  # "modeled_filled" | "pending_next_open"
    modeled_fill_price: Optional[float]
    full_fill: bool              # R7.2: Phase-1 modeled fills are complete-at-once, explicitly marked


def build_order(
    *,
    ticker: str,
    direction: str,              # "long" | "short"
    size_pct_nav: float,         # the GATE-APPROVED final size
    entry_type: str,             # "market_open" | "limit" (Phase-1 vocabulary)
    nav_usd: float,
    price: float,
    market_open: bool,
    limit_price: Optional[float] = None,
) -> ModeledOrder:
    """Deterministic proposal→order arithmetic. Same inputs ⇒ identical order (R3)."""
    if direction not in ("long", "short"):
        raise OrderError(f"invalid direction {direction!r}")
    if entry_type not in ("market_open", "limit"):
        raise OrderError(f"entry type {entry_type!r} outside the Phase-1 vocabulary")
    if price <= 0 or nav_usd <= 0 or size_pct_nav <= 0:
        raise OrderError("non-positive price/NAV/size (fail-closed)")

    target_notional = nav_usd * size_pct_nav / 100.0
    qty = math.floor(target_notional / price)  # whole shares, floor (pinned)
    if qty < 1:
        raise OrderError(
            f"qty rounds to zero ({target_notional:.2f} USD at {price}) — unfillable size (fail-closed)")
    side = "buy" if direction == "long" else "sell"

    if not market_open:
        # R7.1: no fill may be modeled off a closed market's stale price
        return ModeledOrder(ticker, side, qty, entry_type, "day", limit_price,
                            round(qty * price, 2), "pending_next_open", None, False)

    adj = price * HALF_SPREAD_BPS / 1e4  # the WP0 simulate_fill convention at the model's spread
    fill = price + adj if side == "buy" else price - adj
    return ModeledOrder(ticker, side, qty, entry_type, "day", limit_price,
                        round(qty * price, 2), "modeled_filled", round(fill, 6), True)


def log_order(
    order: ModeledOrder,
    *,
    manifest: Any,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    event_log: Any,
) -> dict:
    """Emit the modeled-order event with its ReplayTuple (incl. manifest_version). Returns the stamp."""
    rt = ReplayTuple(trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=decision_ts,
                     agent_id="ORDER-MGR", prompt_version="none",
                     model_version="none", manifest_version=manifest.manifest_version,
                     config_version=load_config().config_version, code_version=code_version)
    event_log.append(event_type="modeled_order", cycle_id=cycle_id, agent_id="ORDER-MGR",
                     payload={"order": asdict(order), "replay_tuple": rt.to_dict()})
    logger.info("modeled_order", symbol=order.symbol, side=order.side, qty=order.qty,
                status=order.status, fill=order.modeled_fill_price)
    return rt.to_dict()
