"""WP4 R4/R5/R7 red tests — breakers, escalation timeout, edge cases. Pure code, fake clocks only.

Gut map: disable a breaker threshold → its injected breach yields nothing → red; disable the
escalation timeout → the unacknowledged breach hangs → red; disable the watchdog → a silent
monitor goes unnoticed → red; drop the exit-only wiring → an add to a stale name passes the gate
→ red.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from graphs.monitor import (
    BreakerStateMachine,
    Escalation,
    HeldPosition,
    MonitorAction,
    Watchdog,
    config_doc_carries_default_derisk,
    monitor_tick,
    validate_escalation_action,
)
from graphs.risk_gate import evaluate

T0 = datetime(2026, 7, 2, 14, 30, tzinfo=timezone.utc)
NAV0 = 1_000_000.0


def _kinds(actions: list[MonitorAction]) -> list[str]:
    return [a.kind for a in actions]


# ── R4: injected breaches fire the §7 breakers ────────────────────────────────────
def test_pod_halve_fires_at_minus_5_boundary_exact():
    """Boundary pinned: dd == 5.0% exactly TRIPS (≤ −threshold)."""
    b = BreakerStateMachine(NAV0)
    assert _kinds(b.tick(950_000.0)) == ["pod_halve_gross"]   # exactly −5.0%
    assert b.state == "normal"                                 # pod action, fund state untouched


def test_pod_halve_does_not_fire_above_boundary():
    b = BreakerStateMachine(NAV0)
    assert b.tick(950_001.0) == []  # −4.9999% — no trip


def test_pod_flatten_at_minus_7_5():
    b = BreakerStateMachine(NAV0)
    kinds = _kinds(b.tick(925_000.0))  # −7.5%
    assert "pod_flatten" in kinds
    assert "fund_derisk" in kinds      # −7.5 ≥ −6 fund derisk too


def test_fund_derisk_transitions_state_for_the_gate():
    b = BreakerStateMachine(NAV0)
    kinds = _kinds(b.tick(940_000.0))  # −6.0% exactly
    assert "fund_derisk" in kinds and b.state == "derisk"


def test_fund_halt_at_minus_10():
    b = BreakerStateMachine(NAV0)
    kinds = _kinds(b.tick(900_000.0))  # −10.0%
    assert kinds == ["fund_halt"] and b.state == "halt"


def test_halt_blocks_gate_approvals_end_to_end():
    """R4's integration requirement: monitor trips HALT → the GATE consumes the state → a clean
    proposal is rejected. Gut the state wiring → the approval passes → red."""
    b = BreakerStateMachine(NAV0)
    b.tick(900_000.0)
    d = evaluate(ticker="MDT", direction="long", size_pct_nav=0.5, nav_usd=900_000.0,
                 price=178.0, adv_usd_20d=493e6, sector="health", book=[],
                 breaker_state=b.state)
    assert not d.approved and d.rule == "breaker_halt"


def test_halt_never_auto_decays_human_recovery_then_cooldown():
    """P12: recovery is human-initiated; re-entry passes through exit-only cooldown for 3 clean
    sessions, during which the gate rejects new entries."""
    b = BreakerStateMachine(NAV0)
    b.tick(900_000.0)
    for _ in range(10):
        b.tick(990_000.0)  # recovered NAV — but HALT must not decay on its own
    assert b.state == "halt"
    b.human_recover()
    assert b.state == "cooldown"
    d = evaluate(ticker="MDT", direction="long", size_pct_nav=0.5, nav_usd=990_000.0,
                 price=178.0, adv_usd_20d=493e6, sector="health", book=[],
                 breaker_state=b.state)
    assert not d.approved and d.rule == "breaker_cooldown"
    b.tick(995_000.0); b.tick(995_000.0)
    assert b.state == "cooldown"          # 2 clean sessions: still exit-only
    b.tick(995_000.0)
    assert b.state == "normal"            # cooldown_cycles = 3 complete


def test_derisk_decays_after_three_clean_sessions():
    b = BreakerStateMachine(NAV0)
    b.tick(940_000.0)
    assert b.state == "derisk"
    b.tick(960_000.0); b.tick(960_000.0)
    assert b.state == "derisk"
    b.tick(960_000.0)
    assert b.state == "normal"


def test_stop_breach_emits_exit_action():
    b = BreakerStateMachine(NAV0)
    pos = [HeldPosition("MDT", 41, stop_price=170.0, direction="long",
                        last_mark=169.5, mark_at=T0)]
    r = monitor_tick(breakers=b, nav_usd=NAV0, positions=pos, now=T0, market_open=True)
    assert "stop_exit" in _kinds(r.actions)


# ── R5: escalation timeout ⇒ default de-risk (fake clock, no sleeps) ───────────────
def test_escalation_timeout_fires_default_derisk():
    e = Escalation(ticker="MDT", created_at=T0)
    assert e.check(T0 + timedelta(minutes=9, seconds=59)) is None      # not yet
    a = e.check(T0 + timedelta(minutes=10))                            # boundary: exactly 10 min
    assert a is not None and a.kind == "escalation_default_derisk" and "50" in a.detail


def test_acknowledged_escalation_never_defaults():
    e = Escalation(ticker="MDT", created_at=T0, acknowledged=True)
    assert e.check(T0 + timedelta(hours=2)) is None


def test_escalation_actions_never_entries_or_increases():
    for ok in ("hold", "reduce", "hedge", "exit"):
        assert validate_escalation_action(ok) == ok
    with pytest.raises(ValueError, match="forbidden"):
        validate_escalation_action("increase")
    with pytest.raises(ValueError, match="forbidden"):
        validate_escalation_action("new_entry")


# ── R7 edge cases ──────────────────────────────────────────────────────────────────
def test_market_closed_tick_skips_breaker_evaluation():
    """R7.1 applied to monitoring: closed-market marks are stale — no breaker transitions."""
    b = BreakerStateMachine(NAV0)
    r = monitor_tick(breakers=b, nav_usd=880_000.0, positions=[], now=T0, market_open=False)
    assert _kinds(r.actions) == ["tick_skipped_market_closed"]
    assert b.state == "normal"  # a −12% mark off a closed market did NOT trip HALT


def test_stale_held_name_flips_exit_only_and_gate_blocks_adds():
    """R7.3: stale mark ⇒ exit-only; the gate rejects an ADD to that name; a stale mark must not
    trigger a stop either. Gut the wiring → the add passes → red."""
    b = BreakerStateMachine(NAV0)
    pos = [HeldPosition("MDT", 41, stop_price=170.0, direction="long",
                        last_mark=169.0, mark_at=T0 - timedelta(minutes=16))]
    r = monitor_tick(breakers=b, nav_usd=NAV0, positions=pos, now=T0, market_open=True)
    assert "stale_exit_only" in _kinds(r.actions)
    assert "stop_exit" not in _kinds(r.actions)     # stale marks decide nothing
    assert r.exit_only_names == {"MDT"}
    d = evaluate(ticker="MDT", direction="long", size_pct_nav=0.5, nav_usd=NAV0,
                 price=178.0, adv_usd_20d=493e6, sector="health", book=[],
                 breaker_state=b.state, exit_only_names=r.exit_only_names)
    assert not d.approved and d.rule == "stale_name_exit_only"


def test_watchdog_halts_on_missed_heartbeat():
    """R7.4: the monitor failing silent is itself a breach — missed heartbeat ⇒ HALT, and the
    gate consumes it end-to-end."""
    b = BreakerStateMachine(NAV0)
    w = Watchdog(max_gap_min=5.0)
    w.beat(T0)
    assert w.check(T0 + timedelta(minutes=4), b) is None
    a = w.check(T0 + timedelta(minutes=6), b)
    assert a is not None and a.kind == "watchdog_halt" and b.state == "halt"
    d = evaluate(ticker="AVGO", direction="long", size_pct_nav=0.5, nav_usd=NAV0,
                 price=250.0, adv_usd_20d=8e9, sector="tech", book=[], breaker_state=b.state)
    assert not d.approved and d.rule == "breaker_halt"


def test_default_derisk_doc_literal_guard():
    """`default_derisk_pct = 50%` is parser-shadowed in config §8 — the constant lives in code,
    guarded here against doc drift."""
    assert config_doc_carries_default_derisk()
