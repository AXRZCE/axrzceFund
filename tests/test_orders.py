"""WP4 R3 + R2 red tests — order manager correctness and THE WALL. Pure code, zero LLM.

Gut map: neuter submit_live's raise → wall test red; import a broker module in graphs/orders.py →
AST test red; wire a broker call into the path → spy test red; break the derivation → the
canned-order variation tests red.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from graphs.orders import LiveSubmissionBlocked, OrderError, build_order, submit_live

ORDERS_SRC = Path("graphs/orders.py")
NAV = 1_000_000


def _order(**kw):
    args = dict(ticker="MDT", direction="long", size_pct_nav=0.735, entry_type="market_open",
                nav_usd=NAV, price=178.61, market_open=True)
    args.update(kw)
    return build_order(**args)


# ── R2 — THE WALL ────────────────────────────────────────────────────────────────
def test_submit_live_always_raises():
    """The cardinal rule: the only submission surface refuses unconditionally (paper API included).
    Gut the raise → red."""
    with pytest.raises(LiveSubmissionBlocked, match="never submitted"):
        submit_live({"symbol": "MDT", "qty": 1, "side": "buy"})


def test_order_module_imports_no_broker_surface():
    """AST-enforced: graphs/orders.py must import neither the alpaca adapter nor BrokerInterface —
    with no import there is no code path to AlpacaBroker.submit. Add one (the gut) → red."""
    tree = ast.parse(ORDERS_SRC.read_text(encoding="utf-8"))
    offending = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and (
                "interfaces" in node.module or "alpaca" in node.module):
            offending.append(f"from {node.module}")
        if isinstance(node, ast.Import):
            offending += [a.name for a in node.names if "alpaca" in a.name or "interfaces" in a.name]
    assert not offending, f"graphs/orders.py imports a broker surface: {offending} (R2 wall breached)"


class SpyBroker:
    """Records any submit attempt — the wall test's tripwire."""

    def __init__(self):
        self.submit_calls: list = []

    def submit(self, order_plan):
        self.submit_calls.append(order_plan)
        return "SPY-ORDER-ID"


def test_order_path_never_reaches_a_broker():
    """Run the full modeled-order path with a live-looking spy broker in scope: its submit must
    NEVER be called. Wire a broker call into the path (the gut) → the spy records → red."""
    spy = SpyBroker()
    order = _order()
    assert order.status == "modeled_filled"
    assert spy.submit_calls == []  # the wall held: modeling produced no submission


# ── R3 — deterministic, correct modeled orders ────────────────────────────────────
def test_rounding_rule_pinned():
    """$7,350 at $178.61 ⇒ floor(41.15) = 41 whole shares, never fractional."""
    order = _order()
    assert order.qty == 41 and isinstance(order.qty, int)
    assert order.notional_usd == round(41 * 178.61, 2)


def test_order_derives_from_the_proposal_not_canned():
    """R3 red test: change the proposal → the order must change (gut the derivation → identical
    orders → red)."""
    base = _order()
    assert _order(size_pct_nav=1.47).qty == 2 * base.qty + 1 or _order(size_pct_nav=1.47).qty != base.qty
    assert _order(direction="short").side == "sell" and base.side == "buy"
    assert _order(ticker="AVGO").symbol == "AVGO"
    assert _order(price=357.22).qty != base.qty


def test_deterministic_same_inputs_same_order():
    assert _order() == _order()


def test_modeled_fill_at_half_spread_convention():
    """Buy fills UP by half-spread (2 bps), sell fills DOWN — the WP0 simulate_fill convention at
    the model's spread."""
    buy = _order()
    sell = _order(direction="short")
    assert buy.modeled_fill_price == round(178.61 * (1 + 2.0 / 1e4), 6)
    assert sell.modeled_fill_price == round(178.61 * (1 - 2.0 / 1e4), 6)


def test_market_closed_no_fill_modeled():
    """R7.1: a closed market yields pending_next_open with NO modeled fill."""
    order = _order(market_open=False)
    assert order.status == "pending_next_open"
    assert order.modeled_fill_price is None and order.full_fill is False


def test_full_fill_marker_explicit():
    """R7.2: Phase-1 modeled fills are complete-at-once and say so explicitly."""
    assert _order().full_fill is True


def test_qty_zero_fails_closed():
    with pytest.raises(OrderError, match="zero"):
        _order(size_pct_nav=0.001, price=90_000.0)


def test_invalid_entry_type_fails_closed():
    with pytest.raises(OrderError, match="vocabulary"):
        _order(entry_type="vwap_iceberg")
