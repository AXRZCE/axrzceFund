"""WP4 R1 red tests — the code gate blocks/clamps every breaching decision, fail-closed.

Gut map: disable the allowance loop → a breaching proposal passes → red; disable the exception
wrapper → a buggy check passes proposals → red; drop the universe floor → a BNC-class name reaches
the order path → red.
"""

from __future__ import annotations

from graphs.risk_gate import GateDecision, Position, config_doc_carries_the_units, evaluate

NAV = 1_000_000
MEGACAP_ADV = 8_000e6  # AVGO-class


def _eval(size, *, book=(), breaker="normal", adv=MEGACAP_ADV, price=250.0,
          direction="long", sector="tech", ticker="AVGO"):
    return evaluate(ticker=ticker, direction=direction, size_pct_nav=size, nav_usd=NAV,
                    price=price, adv_usd_20d=adv, sector=sector, book=list(book),
                    breaker_state=breaker)


def test_clean_proposal_passes_untouched():
    d = _eval(0.735)  # the observed WP3 PM size
    assert d.approved and not d.clamped and d.final_size_pct_nav == 0.735 and d.rule == "ok"


def test_breaching_new_position_clamped_within_ratio():
    """2.5%-new-position cap: 3.0% proposed → 2.5/3.0 = 0.833 ≥ 0.8 ⇒ CLAMP (a trim, not a wrong
    proposal). Gut the gate → 3.0% passes untouched → red."""
    d = _eval(3.0)
    assert d.approved and d.clamped and d.final_size_pct_nav == 2.5 and d.rule == "new_position_limit"


def test_deep_breach_rejected_not_trimmed():
    """6% proposed: the 5% position limit binds FIRST in P7.3 order (before the new-position rule),
    final allowance 2.5% → ratio 0.417 < 0.8 ⇒ REJECT — the proposal was wrong. Gut the gate →
    a 6% order passes → red."""
    d = _eval(6.0)
    assert not d.approved and d.rule == "position_limit"


def test_clamp_ratio_boundary_exactly_08_clamps():
    """Boundary pinned: allowance/proposed == 0.8 exactly ⇒ CLAMP ('may trim up to 20%')."""
    d = _eval(3.125)  # 2.5 / 3.125 == 0.8 exactly
    assert d.approved and d.clamped and d.final_size_pct_nav == 2.5
    assert abs(d.audit["clamp_ratio"] - 0.8) < 1e-9


def test_position_limit_counts_existing_holding():
    """Held 4% of the same name: 5% cap leaves 1.0% allowance; 1.2% proposed → ratio 0.833 ⇒ clamp."""
    book = [Position("AVGO", "tech", 40_000.0)]
    d = _eval(1.2, book=book)
    assert d.approved and d.clamped and d.final_size_pct_nav == 1.0 and d.rule == "position_limit"


def test_sector_cap_binds_on_concentrated_book():
    """19.5% tech gross held: sector cap 20% leaves 0.5%; 1.0% proposed → ratio 0.5 ⇒ REJECT."""
    book = [Position(f"T{i}", "tech", 39_000.0) for i in range(5)]  # 19.5% gross tech
    d = _eval(1.0, book=book)
    assert not d.approved and d.rule == "sector_cap"


def test_net_band_short_side():
    """Net −29.5% held (spread across 5 sectors so nothing else binds): a further 1.0% short
    leaves net allowance 0.5% → ratio 0.5 ⇒ reject on net_band; a long passes."""
    book = [Position(f"S{i}", f"sector{i}", -59_000.0) for i in range(5)]  # net −29.5%
    short = _eval(1.0, book=book, direction="short", sector="sector0", ticker="XYZ")
    assert not short.approved and short.rule == "net_band"
    long_ = _eval(1.0, book=book, direction="long", sector="sector0", ticker="XYZ")
    assert long_.approved


def test_universe_floor_rejects_sub_floor_adv():
    """R1 red test (the BNC/BIOX finding): a $1.0M-ADV name must NEVER reach the order path —
    non-clampable reject. Gut the floor → it passes → red."""
    d = _eval(0.5, adv=1.0e6, ticker="BNC", sector="fin")
    assert not d.approved and d.rule == "universe_floor_adv"


def test_universe_floor_rejects_sub_5_dollar_price():
    d = _eval(0.5, price=4.99)
    assert not d.approved and d.rule == "universe_floor_price"


def test_halt_breaker_rejects_everything():
    d = _eval(0.1, breaker="halt")
    assert not d.approved and d.rule == "breaker_halt"


def test_derisk_breaker_halves_new_entries_as_policy_not_trim():
    """§7 fund_derisk: new-entry ×0.5 is a mandatory policy multiplier — applied even though
    0.5 < min_clamp_ratio (it is not a limit trim)."""
    d = _eval(1.0, breaker="derisk")
    assert d.approved and d.final_size_pct_nav == 0.5
    assert d.audit["derisk_new_entry_mult"] == 0.5


def test_gate_exception_fails_closed():
    """R1: an internal error must REJECT, never pass. A book entry engineered to explode the
    arithmetic (None notional) ⇒ gate_error reject."""
    bad_book = [Position("AVGO", "tech", None)]  # type: ignore[arg-type]
    d = _eval(0.5, book=bad_book)
    assert not d.approved and d.rule == "gate_error"


def test_unknown_breaker_state_fails_closed():
    d = _eval(0.5, breaker="wat")
    assert not d.approved and d.rule == "gate_error"


def test_min_adv_units_guard():
    """The $20M literal parses as 20 → interpreted ×1e6; this guard pins the doc literal so the
    interpretation can't silently drift."""
    assert config_doc_carries_the_units()


def test_adv_participation_never_binds_at_phase1_sizes():
    """Design property (config §6): 2% of a $340M+ ADV name ≥ $6.8M vs a $25k max new position —
    the allowance is >100× the cap, so the rule exists but cannot bind (evidence-checked)."""
    d = _eval(2.5, adv=340e6)  # the THINNEST golden-day name (LULU)
    assert d.audit["allowances_pct_nav"]["adv_participation"] > 100 * 2.5
