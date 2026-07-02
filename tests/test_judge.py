"""WP3 CP4 red tests — R6 VERIF-01-as-judge. Pure code, zero LLM.

Gut map: remove the call-site disjointness loop in judge_family_for → forced same-family passes
silently → red; remove check_judge_grounding → a canned verdict passes → red.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.heterogeneity import HeterogeneityError
from core.manifest import load_manifest
from graphs.judge import (
    JUDGE_ROLE_BY_FAMILY,
    DebateScores,
    JudgeError,
    check_judge_grounding,
    judge_family_for,
)
from graphs.state import Argument, DebateTurn

ROSTER = {"chinese", "openai", "google"}


def test_debate_judge_family_is_disjoint_from_both_debaters():
    """Judged = {chinese BULL, openai BEAR} → the only disjoint family is google."""
    fam = judge_family_for({"chinese", "openai"}, ROSTER)
    assert fam == "google"


def test_forced_same_family_judge_raises_at_call_site():
    """R6 red test: force family(judge)==family(judged) while a disjoint family exists — the
    CALL-SITE assertion must raise. Gut the loop in judge_family_for → silent pass → red."""
    with pytest.raises(HeterogeneityError, match="required where an alternative exists"):
        judge_family_for({"openai"}, ROSTER, override="openai")


def test_no_alternative_is_logged_not_raised():
    assert judge_family_for({"google"}, {"google"}) == "google"  # logged fallback, no raise


def test_resolution_is_deterministic():
    assert judge_family_for({"openai"}, ROSTER) == judge_family_for({"openai"}, ROSTER)


def test_live_manifest_has_a_judge_seat_per_family():
    m = load_manifest()
    for family, role in JUDGE_ROLE_BY_FAMILY.items():
        spec = m.resolve_runtime(role)  # runtime-scoped, resolvable
        assert spec.family == family and spec.tier == "T3"


def _turns():
    return [
        DebateTurn(agent_id="BULL-01", round=1, position="bull",
                   arguments=[Argument(point="revenue acceleration is real and cited at 22.18B",
                                       evidence=["sf1:AVGO:REVENUE:x"], attacks=None)],
                   concessions=["c"], steelman_of_opponent="s"),
        DebateTurn(agent_id="BEAR-01", round=1, position="bear",
                   arguments=[Argument(point="the multiple already prices the acceleration fully",
                                       evidence=["sf1:AVGO:FCF:x"],
                                       attacks="revenue acceleration is real")],
                   concessions=["c"], steelman_of_opponent="s"),
    ]


def _scores(bull_claims, bear_claims):
    return DebateScores.model_validate({
        "bull": {"evidence": 3, "attack_relevance": 2, "concession_honesty": 3,
                 "claims_scored": bull_claims},
        "bear": {"evidence": 3, "attack_relevance": 3, "concession_honesty": 3,
                 "claims_scored": bear_claims},
    })


def test_grounded_verdict_passes():
    s = _scores(["revenue acceleration is real and cited at 22.18B"],
                ["the multiple already prices the acceleration fully"])
    check_judge_grounding(s, _turns())  # no raise


def test_judge_may_quote_concessions_and_steelman():
    """The CP4 smoke's failure mode: the judge legitimately quoted a concession — the grounding
    corpus must cover everything the judge was shown (points, attacks, concessions, steelman)."""
    turns = _turns()
    turns[1] = turns[1].model_copy(update={"concessions": [
        "for a mature heavily asset-intensive retailer the bull's growth framing has some merit"]})
    s = _scores(["revenue acceleration is real and cited at 22.18B"],
                ["for a mature heavily asset-intensive retailer the bull's growth framing"])
    check_judge_grounding(s, turns)  # no raise


def test_canned_verdict_ignoring_transcript_fails():
    """R6 red test: a verdict citing claims that never appeared in the debate is canned."""
    s = _scores(["the company has fortress-balance-sheet dynamics and superb management"],
                ["macro headwinds doom all semiconductor names this decade"])
    with pytest.raises(JudgeError, match="not present in the transcript"):
        check_judge_grounding(s, _turns())


def test_judge_must_cite_at_least_one_claim():
    with pytest.raises(ValidationError):
        _scores([], ["the multiple already prices the acceleration fully"])
