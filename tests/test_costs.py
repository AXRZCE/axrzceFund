"""WP4 R6 (as AMENDED) red tests — the √-impact cost model varies IN-UNIVERSE. Pure code, zero LLM.

Gut map: flatten the impact term → the in-universe sensitivity tests red; resurrect the placeholder
in pm.py → the grep test red. All sensitivity cases use participation ≤ 0.02 — BOTH orders pass the
gate's ADV cap, so the variation the tests demand is variation the fund actually experiences.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.costs import (
    FLOOR_ROUND_TRIP_BPS,
    HALF_SPREAD_BPS,
    IMPACT_ETA_BPS,
    round_trip_cost_bps,
)


def test_params_reratified_values():
    assert HALF_SPREAD_BPS == 2.0 and IMPACT_ETA_BPS == 50.0 and FLOOR_ROUND_TRIP_BPS == 4.0


def test_eta_anchor_reproduces_the_g05_tail_at_the_adv_cap():
    """The stated derivation: model(p = 0.02) ≈ the G0.5 tail (~11 bps)."""
    at_cap = round_trip_cost_bps(0.02 * 1e9, 1e9)  # participation exactly 0.02
    assert abs(at_cap - (4.0 + 50.0 * math.sqrt(0.02))) < 1e-9
    assert 10.0 <= at_cap <= 12.0  # ≈ the +10.4 bps observed tail


def test_in_universe_sensitivity_both_orders_gate_passable():
    """R6 red test (the ruling's case): $200k in a $25M-ADV name (p=0.008) vs $10k in a $1B-ADV
    name (p=1e-5) — both ≤ 0.02, both pass the gate; the larger-in-thinner MUST cost strictly
    more. Flat model → red."""
    big_thin = round_trip_cost_bps(200_000, 25e6)     # 4 + 50·√0.008 ≈ 8.47
    small_thick = round_trip_cost_bps(10_000, 1e9)    # 4 + 50·√1e-5 ≈ 4.16
    assert 200_000 / 25e6 <= 0.02 and 10_000 / 1e9 <= 0.02  # in-universe by construction
    assert big_thin > small_thick > FLOOR_ROUND_TRIP_BPS


def test_every_real_trade_prices_above_the_floor():
    """The floor is a degenerate-input guard BELOW the in-universe range — the WP3-observed trades
    (0.5–0.735% of $1M NAV in $340M–$8B-ADV names) all price above 4 bps, and none at a constant."""
    observed = [
        round_trip_cost_bps(7_350, 493e6),   # the MDT proposal
        round_trip_cost_bps(5_000, 1_121e6),  # a contested-capped size in COST
        round_trip_cost_bps(7_350, 8_048e6),  # the same size in AVGO
    ]
    assert all(c > FLOOR_ROUND_TRIP_BPS for c in observed)
    assert len(set(observed)) == len(observed)  # per-trade: all DIFFERENT (no constant)


def test_in_universe_monotonicity():
    """Strictly increasing in size, strictly decreasing in liquidity — inside the reachable range."""
    assert round_trip_cost_bps(20_000, 100e6) > round_trip_cost_bps(10_000, 100e6)
    assert round_trip_cost_bps(10_000, 50e6) > round_trip_cost_bps(10_000, 200e6)


def test_floor_clamps_degenerate_inputs():
    """A zero-notional (degenerate) order clamps to the pure double-spread floor."""
    assert round_trip_cost_bps(0.0, 1e9) == FLOOR_ROUND_TRIP_BPS


def test_nonpositive_adv_fails_closed():
    with pytest.raises(ValueError, match="adv"):
        round_trip_cost_bps(10_000, 0.0)


def test_placeholder_gone_from_pm():
    """The WP3 20 bps placeholder stays DELETED; the edge check has no default cost."""
    src = Path("graphs/pm.py").read_text(encoding="utf-8")
    assert "ASSUMED_ROUND_TRIP_COST_BPS" not in src
    assert "round_trip_cost_bps: float)" in src


def test_pm_edge_check_consumes_the_model():
    src = Path("graphs/pm.py").read_text(encoding="utf-8")
    assert "from core.costs import round_trip_cost_bps" in src
    assert "check_edge(" in src


def test_config_doc_carries_the_amended_params():
    """Doc-literal guard (the §11 discipline): configuration.md §6 states the amended values."""
    raw = Path("docs/configuration.md").read_text(encoding="utf-8")
    assert "`cost_impact_eta_bps = 50`" in raw
    assert "`cost_floor_round_trip_bps = 4`" in raw
    assert "`cost_half_spread_bps = 2`" in raw
