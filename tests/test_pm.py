"""WP3 CP3 red tests — R4 contested mechanics + R5 PM discipline. Pure code, zero LLM.

Gut map: disable the contested haircut → test_contested_haircut_applies_when_cap_does_not_bind red;
disable the contested cap → test_contested_cap_binds_after_haircut red; drop the override guard →
override tests red; drop check_ballot_grounding → canned-PM test red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.event_log import EventLog
from graphs.pm import (
    HAIRCUTS,
    EdgeError,
    OverrideError,
    PMError,
    check_ballot_grounding,
    check_edge,
    check_override,
    conviction_factor,
    reconstruct_decision,
    size_position,
)
from graphs.state import BallotSummary


def test_haircut_table_matches_configuration_md():
    """The ×-literals defeat the config parser, so the table lives in code — this guard keeps the
    code and configuration.md §5 from drifting apart silently."""
    raw = Path("docs/configuration.md").read_text(encoding="utf-8")
    assert "contested = ×0.5" in raw and HAIRCUTS["contested"] == 0.5
    assert "regime_mismatch = ×0.7" in raw and HAIRCUTS["regime_mismatch"] == 0.7
    assert "unresolved_bear_crux = ×0.7" in raw and HAIRCUTS["unresolved_bear_crux"] == 0.7
    assert "liquidity_thin = ×0.8" in raw and HAIRCUTS["liquidity_thin"] == 0.8


# ── R4: contested ⇒ BOTH the ×0.5 haircut AND the ≤0.5% cap ───────────────────────
def test_contested_cap_binds_after_haircut():
    """conviction 1.0 → base 1.0 × cf 1.5 = 1.5 → contested ×0.5 = 0.75 → cap → 0.5.
    Gut the CAP → final 0.75 → red."""
    size, audit = size_position(conviction=1.0, contested=True)
    assert audit["haircuts"]["contested"] == 0.5           # the haircut fired
    assert audit["caps"]["contested_size_cap_pct_nav"] == 0.5  # AND the cap bound after it
    assert size == 0.5


def test_contested_haircut_applies_when_cap_does_not_bind():
    """conviction 0.2 → cf 0.7 → 0.7 → contested ×0.5 = 0.35 (< 0.5, cap silent).
    Gut the HAIRCUT → final 0.5 (capped from 0.7) ≠ 0.35 → red."""
    size, audit = size_position(conviction=0.2, contested=True)
    assert audit["haircuts"]["contested"] == 0.5
    assert "contested_size_cap_pct_nav" not in audit["caps"]
    assert abs(size - 0.35) < 1e-9


def test_non_contested_applies_neither():
    size, audit = size_position(conviction=1.0, contested=False)
    assert size == 1.5                       # base × cf only
    assert audit["haircuts"] == {} and "contested_size_cap_pct_nav" not in audit["caps"]


def test_debate_failed_cap():
    size, audit = size_position(conviction=1.0, contested=False, debate_failed=True)
    assert size == 0.75 and audit["caps"]["undebated_size_cap_pct_nav"] == 0.75


def test_unresolved_bear_crux_haircut():
    size, _ = size_position(conviction=1.0, contested=False, unresolved_bear_crux=True)
    assert abs(size - 1.5 * 0.7) < 1e-9


def test_haircuts_stack_multiplicatively_downward():
    size, audit = size_position(conviction=1.0, contested=True, unresolved_bear_crux=True)
    # 1.5 × 0.5 × 0.7 = 0.525 → contested cap 0.5 binds
    assert size == 0.5 and set(audit["haircuts"]) == {"contested", "unresolved_bear_crux"}


def test_conviction_factor_range():
    assert conviction_factor(0.0) == 0.5 and conviction_factor(1.0) == 1.5
    assert conviction_factor(2.0) == 1.5  # clipped — enthusiasm never multiplies unboundedly


# ── R5: edge, override guard, grounding, replay ───────────────────────────────────
def test_edge_below_multiple_rejected():
    """WP4 R6: the cost is the MODEL's output, supplied explicitly (no default constant).
    At the 6 bps floor the bar is 18 bps."""
    with pytest.raises(EdgeError, match="round-trip"):
        check_edge(17.9, round_trip_cost_bps=6.0)
    check_edge(18.0, round_trip_cost_bps=6.0)  # boundary: exactly the multiple passes
    with pytest.raises(EdgeError):
        check_edge(25.0, round_trip_cost_bps=9.0)  # thinner name, higher bar (27)


def test_override_without_rebuttal_rejected():
    with pytest.raises(OverrideError, match="without\\s+a written rebuttal|rebuttal"):
        check_override(direction="short", ballot_direction="long", rebuttal=None,
                       prior_overrides_this_month=0)


def test_override_with_rebuttal_allowed_and_flagged():
    assert check_override(direction="short", ballot_direction="long",
                          rebuttal="The majority's strongest crux (durable CAGR) fails because …",
                          prior_overrides_this_month=0) is True
    assert check_override(direction="long", ballot_direction="long", rebuttal=None,
                          prior_overrides_this_month=0) is False  # not an override


def test_override_monthly_cap_enforced():
    with pytest.raises(OverrideError, match="cap"):
        check_override(direction="short", ballot_direction="long", rebuttal="valid rebuttal",
                       prior_overrides_this_month=2)


def test_canned_pm_ballot_summary_rejected():
    """R5: the proposal's attached ballot_summary must BE the computed tally — a canned decision
    carrying a fabricated summary fails. Gut check_ballot_grounding → red."""
    tallied = BallotSummary(weighted_score=1.15, margin=0.2637, dissent_summary="BEAR-01 voted short",
                            contested=False)
    canned = BallotSummary(weighted_score=0.5, margin=0.2, dissent_summary="stub", contested=False)
    with pytest.raises(PMError, match="canned"):
        check_ballot_grounding(canned, tallied)
    check_ballot_grounding(tallied.model_copy(), tallied)  # control: the real tally passes


def test_replay_reads_stored_decision_no_llm(tmp_path):
    """R5 replay: reconstruct_decision takes ONLY the event log — no client, no manifest, no
    model. (The manifest-hash identity property is pinned by tests/test_replay.py.)"""
    el = EventLog(tmp_path / "ev.db")
    payload = {"proposal": {"ticker": "AVGO", "direction": "long", "size_pct_nav": 0.5},
               "sizing_audit": {"haircuts": {"contested": 0.5}}, "is_override": False,
               "replay_tuple": {"manifest_version": "abc123def456"}}
    el.append(event_type="proposal_written", cycle_id="c1", agent_id="PM-01", payload=payload)
    got = reconstruct_decision(el, "c1")
    assert got["event_type"] == "proposal_written"
    assert got["proposal"]["size_pct_nav"] == 0.5
    assert got["replay_tuple"]["manifest_version"] == "abc123def456"
    import inspect
    params = inspect.signature(reconstruct_decision).parameters
    assert set(params) == {"event_log", "cycle_id"}  # structurally client-free: replay never re-calls
