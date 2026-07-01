"""WP3 CP2 red tests — debate integrity (R2). All pure code, zero LLM.

Each test names the gut that turns it red: delete/disable the corresponding check in
graphs/debate.py and the test fails (DID NOT RAISE). Standing anti-hoax practice.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.heterogeneity import HeterogeneityError
from core.manifest import ManifestError, load_manifest
from graphs.debate import (
    DebateGroundingError,
    DebateRoundCapError,
    DebateVoided,
    allowed_doc_ids,
    check_capitulation,
    check_grounding,
    check_mod_neutrality,
    check_round_cap,
    preflight,
)
from graphs.state import Argument, ClosingStatement, DebateTurn

DOC = "sf1:AVGO:REVENUE:2026-04-30"


def _turn(agent, position, rnd=1, points=None, attacks="the bull's claim 1", evidence=(DOC,)):
    return DebateTurn(
        agent_id=agent, round=rnd, position=position,
        arguments=[Argument(point=p, evidence=list(evidence), attacks=attacks)
                   for p in (points or [f"{agent} r{rnd} point"])],
        concessions=["fair point on margins"], steelman_of_opponent="their best case is X")


def _closing(agent, position, conviction=0.7):
    return ClosingStatement(agent_id=agent, position=position,
                            strongest_points=["p1", "p2", "p3"], conviction=conviction)


def _clean_debate():
    turns = [
        _turn("BULL-01", "bull", 1, ["revenue acceleration is real and cited"], attacks=None),
        _turn("BEAR-01", "bear", 1, ["multiple already prices the acceleration in fully"]),
    ]
    closings = [_closing("BULL-01", "bull"), _closing("BEAR-01", "bear")]
    return turns, closings


# ── R2 red test 1: sycophantic BEAR → debate VOIDED (gut: check_capitulation) ─────
def test_sycophantic_bear_echo_voids_debate():
    """BEAR echoing the BULL's argument text = agreeing, not opposing → void."""
    turns = [
        _turn("BULL-01", "bull", 1, ["revenue acceleration is real and durable this cycle"],
              attacks=None),
        _turn("BEAR-01", "bear", 1, ["revenue acceleration is real and durable this cycle"]),
    ]
    with pytest.raises(DebateVoided, match="echoes"):
        check_capitulation(turns, [_closing("BULL-01", "bull"), _closing("BEAR-01", "bear")])


def test_sycophantic_bear_position_flip_voids_debate():
    """A BEAR turn arguing position='bull' is capitulation (P4.2 role flip)."""
    turns = [_turn("BULL-01", "bull", 1, attacks=None), _turn("BEAR-01", "bull", 1)]
    with pytest.raises(DebateVoided, match="role flip"):
        check_capitulation(turns, [])


def test_bear_closing_on_bull_side_voids_debate():
    """Closing must argue the ASSIGNED side at full strength (P4.2)."""
    turns, _ = _clean_debate()
    with pytest.raises(DebateVoided, match="closing"):
        check_capitulation(turns, [_closing("BULL-01", "bull"), _closing("BEAR-01", "bull")])


def test_bear_never_attacking_voids_debate():
    """A bear that never attacks anything is agreeing by omission."""
    turns = [
        _turn("BULL-01", "bull", 1, attacks=None),
        _turn("BEAR-01", "bear", 1, ["some vague caution"], attacks=None),
    ]
    with pytest.raises(DebateVoided, match="zero attack"):
        check_capitulation(turns, [])


def test_clean_debate_is_not_voided():
    """Control: genuinely divergent turns + on-side closings pass."""
    turns, closings = _clean_debate()
    check_capitulation(turns, closings)  # no raise


# ── R2 red test 2: same-family debaters → HeterogeneityError at entry (gut: preflight) ──
def test_same_family_debaters_raise_at_preflight(tmp_path: Path):
    yaml = """
roles:
  BULL-01:
    family: openai
    tier: T2
    model_version: openai/gpt-5.4
    cutoff: 2026-03-05
    provider: {only: [openai], allow_fallbacks: false}
  BEAR-01:
    family: openai
    tier: T2
    model_version: openai/gpt-5.4
    cutoff: 2026-03-05
    provider: {only: [openai], allow_fallbacks: false}
  MOD-01:
    family: google
    tier: T2
    model_version: google/gemini-3.1-pro-preview
    cutoff: 2026-02-19
    provider: {only: [google-vertex], allow_fallbacks: false}
"""
    p = tmp_path / "samefam.yaml"
    p.write_text(yaml)
    with pytest.raises(HeterogeneityError, match="arguing with itself"):
        preflight(load_manifest(p))


def test_validation_scoped_bull_cannot_be_seated(tmp_path: Path):
    """preflight resolves on the RUNTIME path — a validation-scoped BULL-01 fail-closes."""
    yaml = """
roles:
  BULL-01:
    family: chinese
    tier: T2
    scope: validation
    model_version: z-ai/glm-5.2
    cutoff: 2026-06-16
    provider: {only: [together], allow_fallbacks: false}
  BEAR-01:
    family: openai
    tier: T2
    model_version: openai/gpt-5.4
    cutoff: 2026-03-05
    provider: {only: [openai], allow_fallbacks: false}
  MOD-01:
    family: google
    tier: T2
    model_version: google/gemini-3.1-pro-preview
    cutoff: 2026-02-19
    provider: {only: [google-vertex], allow_fallbacks: false}
"""
    p = tmp_path / "valscope.yaml"
    p.write_text(yaml)
    with pytest.raises(ManifestError, match="validation-only"):
        preflight(load_manifest(p))


def test_live_manifest_preflight_passes():
    """Control: the committed manifest's live roster passes preflight (GLM/openai/google)."""
    bull, bear, mod = preflight(load_manifest())
    assert bull.model_version == "z-ai/glm-5.2" and bear.family == "openai" and mod.family == "google"


# ── R2 red test 3: a 4th round → round-cap red (gut: check_round_cap) ─────────────
def test_fourth_round_breaks_round_cap():
    turns = [_turn("BULL-01", "bull", r, attacks=None) for r in (1, 2, 3, 4)]
    with pytest.raises(DebateRoundCapError, match="max_debate_rounds"):
        check_round_cap(turns, max_rounds=3)
    check_round_cap(turns[:3], max_rounds=3)  # control: 3 rounds pass


# ── R2 red test 4: out-of-set doc_id → grounding red (gut: check_grounding) ───────
def test_out_of_set_citation_fails_grounding():
    memos = [{"agent_id": "FUND-TECH",
              "key_claims": [{"claim": "c", "evidence": [DOC], "claim_type": "fact"}]}]
    allowed = allowed_doc_ids(memos)
    ok = [_turn("BULL-01", "bull", 1, evidence=(DOC,), attacks=None)]
    check_grounding(ok, allowed)  # control
    bad = [_turn("BEAR-01", "bear", 1, evidence=("sf1:FAKE:INVENTED:2099-01-01",))]
    with pytest.raises(DebateGroundingError, match="outside the verified-memo"):
        check_grounding(bad, allowed)


# ── R2 red test 5: MOD-01 carrying a stance → neutrality red (gut: extra=forbid) ──
def test_mod_summary_with_stance_field_rejected():
    raw = {"resolved_points": ["p"], "unresolved_cruxes": ["c"],
           "premortem": {"failure_scenarios": [
               {"scenario": "s", "early_warning_indicator": "watch DSO"}]},
           "process_flags": [], "stance": "long"}  # ← smuggled stance
    with pytest.raises(ValidationError):
        check_mod_neutrality(raw)


def test_mod_premortem_without_observable_indicator_rejected():
    raw = {"resolved_points": [], "unresolved_cruxes": ["c"],
           "premortem": {"failure_scenarios": [{"scenario": "s", "early_warning_indicator": "  "}]},
           "process_flags": []}
    with pytest.raises(Exception, match="unfinished|indicator"):
        check_mod_neutrality(raw)


def test_mod_clean_summary_passes():
    raw = {"resolved_points": ["both accept revenue grew"],
           "unresolved_cruxes": ["is the multiple justified"],
           "premortem": {"failure_scenarios": [
               {"scenario": "guide-down next quarter", "early_warning_indicator": "channel checks"}]},
           "process_flags": []}
    s = check_mod_neutrality(raw)
    assert s.unresolved_cruxes == ["is the multiple justified"]
