"""Round-trip cost model (WP4 R6) — retires WP3's flagged 20 bps placeholder.

    round_trip_cost_bps = max(2 · half_spread_bps + impact_bps, floor)
    impact_bps          = impact_coeff · participation_fraction(order_notional / ADV_20d)

Parameters live in configuration.md §6 (ratified at WP4-OPEN; a missing param is a §11 build
error): `cost_half_spread_bps = 2` (≈1.0× the G0.5 measured mean-abs divergence, 1.94 bps over
n=20 fills; the +10.4 bps outlier is known tail risk the floor partially covers),
`cost_impact_coeff_bps = 25`, `cost_floor_round_trip_bps = 6` (so the P6 edge gate, 3×, demands
≥18 bps of expected edge).

**INTERIM by ruling:** mandatory recalibration at WP6 from the dry-run week's logged IEX quotes,
then at WP7 from real paper fills (wp4-done-criteria R6 — a WP6 gate item).

Properties the red tests pin: size-monotone (a larger order costs ≥, strictly > beyond the floor),
liquidity-monotone (thinner name costs ≥), floor binds at megacap Phase-1 sizes.
"""

from __future__ import annotations

from core.config import param_number

HALF_SPREAD_BPS = param_number("cost_half_spread_bps")            # 2
IMPACT_COEFF_BPS = param_number("cost_impact_coeff_bps")          # 25
FLOOR_ROUND_TRIP_BPS = param_number("cost_floor_round_trip_bps")  # 6


def participation_fraction(order_notional_usd: float, adv_usd_20d: float) -> float:
    if adv_usd_20d <= 0:
        raise ValueError(f"adv_usd_20d must be positive (got {adv_usd_20d}) — fail-closed")
    return max(0.0, order_notional_usd) / adv_usd_20d


def round_trip_cost_bps(order_notional_usd: float, adv_usd_20d: float) -> float:
    """Modeled round-trip cost in bps for THIS order in THIS name."""
    impact = IMPACT_COEFF_BPS * participation_fraction(order_notional_usd, adv_usd_20d)
    return max(2.0 * HALF_SPREAD_BPS + impact, FLOOR_ROUND_TRIP_BPS)
