"""The code risk gate (WP4 R1) — P7's L5: last, binding, emotion-free, FAIL-CLOSED.

Evaluates a gate-input (the PM proposal's ticker/direction/size + market context + the current
book + breaker state) against configuration.md's §6 table in **P7.3's fixed order**:

    universe floors (ADV/price) → position limit → sector cap → gross/net exposure →
    ADV participation → breaker state

Semantics (pinned by the red tests):
  - **Non-clampable rules** (universe floors, HALT breaker) ⇒ REJECT with a machine-readable rule id.
  - **Sizing rules** each yield a max-allowed size; the binding rule is the FIRST in P7.3 order
    whose allowance is below the proposal. `final/proposed ≥ min_clamp_ratio (0.8)` ⇒ CLAMP to the
    allowance ("a 5% trim is a clamp"); deeper ⇒ REJECT ("a 60% trim means the proposal was wrong").
    Boundary: ratio == 0.8 exactly ⇒ CLAMP.
  - **`derisk` breaker state** (§7 fund −6%): new-entry size ×0.5 as a mandatory POLICY multiplier
    applied before the limit checks — not a trim, so not subject to min_clamp_ratio.
  - **Any exception inside a check ⇒ REJECT** (`gate_error`) — gate code errors fail closed (P7).
  - There is NO human override of the gate mid-cycle; a wrong limit is a configuration.md change
    via P11, never a bypass.

All numeric limits read from configuration.md via `param_number` (§11: absent ⇒ build error).
The gate is pure code — no LLM, no network; the caller logs the GateDecision with a ReplayTuple.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from core.config import param_number

logger = structlog.get_logger()

MAX_POSITION_PCT_NAV = param_number("max_position_pct_nav")            # 5
MAX_NEW_POSITION_PCT_NAV = param_number("max_new_position_pct_nav")    # 2.5
MAX_SECTOR_PCT_NAV = param_number("max_sector_pct_nav")                # 20
MAX_GROSS_PCT_NAV = param_number("max_gross")                          # 150
NET_BAND_PCT_NAV = param_number("net_band")                            # 30 (±)
MAX_ADV_PARTICIPATION_PCT = param_number("max_adv_participation_pct")  # 2
MIN_CLAMP_RATIO = param_number("min_clamp_ratio")                      # 0.8
MIN_PRICE_USD = param_number("min_price")                              # 5.00
# configuration.md §1 writes "$20M"; the parser reads the leading 20 → interpret as millions.
# tests/test_risk_gate.py guards the doc literal so this interpretation can't silently drift.
MIN_ADV_USD = param_number("min_adv_usd") * 1e6                        # $20,000,000
DERISK_NEW_ENTRY_MULT = 0.5                                            # §7 fund_derisk: new-entry sizes ×0.5

BREAKER_STATES = ("normal", "derisk", "halt")


@dataclass(frozen=True)
class Position:
    ticker: str
    sector: str
    signed_notional_usd: float  # + long / − short


@dataclass(frozen=True)
class GateDecision:
    approved: bool
    clamped: bool
    final_size_pct_nav: float
    rule: str          # machine-readable id of the binding/rejecting rule ("ok" when untouched)
    reason: str
    audit: dict = field(default_factory=dict)


def _reject(rule: str, reason: str, audit: dict) -> GateDecision:
    logger.info("gate_reject", rule=rule, reason=reason)
    return GateDecision(False, False, 0.0, rule, reason, audit)


def evaluate(
    *,
    ticker: str,
    direction: str,               # "long" | "short"
    size_pct_nav: float,
    nav_usd: float,
    price: float,
    adv_usd_20d: float,
    sector: str,
    book: list[Position],
    breaker_state: str = "normal",
) -> GateDecision:
    """Run the P7.3 gate. Never raises: any internal error returns a fail-closed REJECT."""
    audit: dict = {"proposed_size_pct_nav": size_pct_nav, "breaker_state": breaker_state}
    try:
        if breaker_state not in BREAKER_STATES:
            return _reject("gate_error", f"unknown breaker_state {breaker_state!r} (fail-closed)", audit)
        if size_pct_nav <= 0 or nav_usd <= 0:
            return _reject("gate_error", "non-positive size or NAV (fail-closed)", audit)

        # ── 5-pre. breaker policy multiplier (derisk: new-entry ×0.5; not a trim) ──────
        working = size_pct_nav
        if breaker_state == "derisk":
            working = size_pct_nav * DERISK_NEW_ENTRY_MULT
            audit["derisk_new_entry_mult"] = DERISK_NEW_ENTRY_MULT

        # ── 0. universe floors — non-clampable ──────────────────────────────────────
        if adv_usd_20d < MIN_ADV_USD:
            return _reject("universe_floor_adv",
                           f"ADV ${adv_usd_20d:,.0f} < ${MIN_ADV_USD:,.0f} floor", audit)
        if price < MIN_PRICE_USD:
            return _reject("universe_floor_price", f"price {price} < ${MIN_PRICE_USD} floor", audit)

        # ── 5. HALT — non-clampable (checked before sizing math can matter) ─────────
        if breaker_state == "halt":
            return _reject("breaker_halt", "fund breaker HALT: no approvals until human review (P12)", audit)

        # ── sizing rules, P7.3 order; each yields a max-allowed size in pct-NAV ──────
        sign = 1.0 if direction == "long" else -1.0
        existing_same = sum(abs(p.signed_notional_usd) for p in book if p.ticker == ticker)
        existing_same_pct = 100.0 * existing_same / nav_usd
        sector_gross_pct = 100.0 * sum(abs(p.signed_notional_usd) for p in book
                                       if p.sector == sector) / nav_usd
        gross_pct = 100.0 * sum(abs(p.signed_notional_usd) for p in book) / nav_usd
        net_pct = 100.0 * sum(p.signed_notional_usd for p in book) / nav_usd

        allowances: list[tuple[str, float]] = [
            ("position_limit", MAX_POSITION_PCT_NAV - existing_same_pct),
            # every Phase-1 proposal on a name we don't hold is a NEW position
            ("new_position_limit",
             MAX_NEW_POSITION_PCT_NAV if existing_same == 0 else MAX_POSITION_PCT_NAV - existing_same_pct),
            ("sector_cap", MAX_SECTOR_PCT_NAV - sector_gross_pct),
            ("gross_cap", MAX_GROSS_PCT_NAV - gross_pct),
            ("net_band",
             (NET_BAND_PCT_NAV - net_pct) if sign > 0 else (NET_BAND_PCT_NAV + net_pct)),
            ("adv_participation",
             100.0 * (MAX_ADV_PARTICIPATION_PCT / 100.0) * adv_usd_20d / nav_usd),
        ]
        audit["allowances_pct_nav"] = {r: round(a, 6) for r, a in allowances}

        final = working
        binding: Optional[str] = None
        for rule, allowed in allowances:  # FIRST rule in P7.3 order that binds attributes the decision
            if allowed < final:
                if binding is None:
                    binding = rule
                final = max(0.0, allowed)

        if binding is None:
            return GateDecision(True, breaker_state == "derisk", round(working, 6), "ok",
                                "within all limits" + (" (derisk ×0.5 applied)" if breaker_state == "derisk" else ""),
                                audit)

        ratio = final / working if working > 0 else 0.0
        audit["clamp_ratio"] = round(ratio, 6)
        if final > 0 and round(ratio, 9) >= MIN_CLAMP_RATIO:  # boundary: exactly 0.8 ⇒ CLAMP
            logger.info("gate_clamp", rule=binding, from_pct=working, to_pct=final)
            return GateDecision(True, True, round(final, 6), binding,
                                f"clamped {working:.4f}% → {final:.4f}% (ratio {ratio:.3f} ≥ "
                                f"{MIN_CLAMP_RATIO}) by {binding}", audit)
        return _reject(binding,
                       f"needs {working:.4f}% → {final:.4f}% (ratio {ratio:.3f} < {MIN_CLAMP_RATIO}) "
                       f"— the proposal was wrong, not trimmable (P7.3)", audit)
    except Exception as e:  # gate code errors FAIL CLOSED (P7) — never pass a proposal on a bug
        return _reject("gate_error", f"exception in gate evaluation: {e} (fail-closed)", audit)


def config_doc_carries_the_units() -> bool:
    """Guard for the $20M-parses-as-20 interpretation (used by the pin test)."""
    raw = Path("docs/configuration.md").read_text(encoding="utf-8")
    return "`min_adv_usd = $20M`" in raw
