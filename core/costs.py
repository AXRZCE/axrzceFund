"""Round-trip cost model (WP4 R6, as AMENDED) — square-root impact law.

    round_trip_cost_bps = max(2 · half_spread_bps + η · √participation_fraction, floor)

**Amendment history (Akshar's R6 re-ratification, recorded in wp4-done-criteria):** the first
model used LINEAR impact (25 × participation, floor 6) and was found **degenerate in the
gate-reachable universe** — its variable region began above ~8% participation while the gate caps
participation at 2%, so every real trade priced at the constant floor. Ruled REJECTED: the model
must genuinely vary per trade in-universe; degenerate-in-practice implementations don't get
grandfathered.

Parameters (configuration.md §6; absent ⇒ §11 build error):
  - `cost_half_spread_bps = 2` — ≈1.0× the G0.5 measured mean-abs divergence (1.94 bps, n=20);
  - `cost_impact_eta_bps = 50` — anchored: model(p = 0.02, the ADV-cap boundary) ≈ the G0.5 tail
    (~11 bps) ⇒ η = (11−4)/√0.02 = 49.5 → 50;
  - `cost_floor_round_trip_bps = 4` — the pure double-spread: a degenerate-input guard BELOW the
    in-universe range (any p>0 prices above it; it must never bind a real trade).

In-universe span: 4.5 bps @ p=1e-4 → 5.6 @ 1e-3 → 9.0 @ 0.01 → 11.1 @ 0.02.
**INTERIM by ruling:** η and half_spread re-derived at WP6 from logged IEX quotes (a WP6 gate
item), then at WP7 from real paper fills.

Properties the red tests pin (IN-UNIVERSE, participation ≤ 0.02 — both orders gate-passable):
larger-in-thinner costs strictly more than smaller-in-thicker; every real trade prices above the
floor; degenerate inputs clamp to the floor.
"""

from __future__ import annotations

import math

from core.config import param_number

HALF_SPREAD_BPS = param_number("cost_half_spread_bps")            # 2
IMPACT_ETA_BPS = param_number("cost_impact_eta_bps")              # 50 (√-law coefficient)
FLOOR_ROUND_TRIP_BPS = param_number("cost_floor_round_trip_bps")  # 4 (= pure double-spread)


def participation_fraction(order_notional_usd: float, adv_usd_20d: float) -> float:
    if adv_usd_20d <= 0:
        raise ValueError(f"adv_usd_20d must be positive (got {adv_usd_20d}) — fail-closed")
    return max(0.0, order_notional_usd) / adv_usd_20d


def round_trip_cost_bps(order_notional_usd: float, adv_usd_20d: float) -> float:
    """Modeled round-trip cost in bps for THIS order in THIS name (√-impact, floored)."""
    p = participation_fraction(order_notional_usd, adv_usd_20d)
    return max(2.0 * HALF_SPREAD_BPS + IMPACT_ETA_BPS * math.sqrt(p), FLOOR_ROUND_TRIP_BPS)
