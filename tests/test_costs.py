"""WP4 R6 red tests — the real cost model. Pure code, zero LLM.

Gut map: return a constant → monotonicity tests red; drop the floor → floor test red;
resurrect the placeholder in pm.py → the grep test red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.costs import FLOOR_ROUND_TRIP_BPS, HALF_SPREAD_BPS, round_trip_cost_bps


def test_params_ratified_values():
    assert HALF_SPREAD_BPS == 2.0 and FLOOR_ROUND_TRIP_BPS == 6.0


def test_floor_binds_at_megacap_phase1_sizes():
    """$7.4k order (0.735% of $1M NAV) in a ~$493M-ADV name: participation ~1.5e-5 ⇒ impact ~0 ⇒
    the 6 bps floor binds — required edge = 18 bps."""
    assert round_trip_cost_bps(7_350, 493e6) == 6.0


def test_size_monotone_beyond_floor():
    """R6 red test: a larger order costs strictly more once past the floor (gut to a constant → red)."""
    thin_adv = 20e6  # the universe floor name
    small = round_trip_cost_bps(2_000_000, thin_adv)   # participation 0.10 → 4 + 2.5 = 6.5
    large = round_trip_cost_bps(4_000_000, thin_adv)   # participation 0.20 → 4 + 5.0 = 9.0
    assert large > small > FLOOR_ROUND_TRIP_BPS


def test_liquidity_monotone():
    """The same order in a thinner name costs strictly more (beyond the floor)."""
    order = 3_000_000
    assert round_trip_cost_bps(order, 20e6) > round_trip_cost_bps(order, 40e6) >= FLOOR_ROUND_TRIP_BPS


def test_nonpositive_adv_fails_closed():
    with pytest.raises(ValueError, match="adv"):
        round_trip_cost_bps(10_000, 0.0)


def test_placeholder_gone_from_pm():
    """R6 red test: the WP3 20 bps placeholder constant is DELETED from graphs/pm.py; the edge
    check has no default cost (the caller must supply the model output)."""
    src = Path("graphs/pm.py").read_text(encoding="utf-8")
    assert "ASSUMED_ROUND_TRIP_COST_BPS" not in src
    assert "round_trip_cost_bps: float)" in src  # no default value in check_edge's signature


def test_pm_edge_check_consumes_the_model():
    """pm.run_pm must call core.costs.round_trip_cost_bps (source-level pin)."""
    src = Path("graphs/pm.py").read_text(encoding="utf-8")
    assert "from core.costs import round_trip_cost_bps" in src
    assert "check_edge(" in src
