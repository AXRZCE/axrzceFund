"""WP3 CP2 red tests — P5 ballot tally (R3). Pure code, zero LLM.

The distinctness tests ARE the gut-detector for the tally: replace `tally` with any hardcoded
BallotSummary (as the WP1 deep_loop.py:135 stub did) and two different vote sets return the same
summary → red.
"""

from __future__ import annotations

import pytest

from graphs.ballot import tally
from graphs.state import Ballot

T = 0.20  # configuration.md §4 ballot_margin_threshold


def _v(voter, stance, conviction):
    return Ballot(voter=voter, stance=stance, conviction=conviction, size_inclination="standard")


def test_distinct_vote_sets_yield_distinct_summaries():
    """R3 red test: the summary must be COMPUTED from the votes (gut the tally → red)."""
    a, da = tally([_v("FUND-TECH", "long", 0.8), _v("TECH-01", "long", 0.7),
                   _v("BEAR-01", "short", 0.3)], margin_threshold=T)
    b, db = tally([_v("FUND-TECH", "short", 0.9), _v("TECH-01", "short", 0.6),
                   _v("BULL-01", "long", 0.4)], margin_threshold=T)
    assert (a.weighted_score, a.margin, a.dissent_summary) != (b.weighted_score, b.margin,
                                                               b.dissent_summary)
    assert da == "long" and db == "short"


def test_tally_matches_p5_formula_exactly():
    """score(d) = Σ w·conviction·1[stance=d] with w=1; margin normalized to total cast weight."""
    votes = [_v("A", "long", 0.8), _v("B", "long", 0.4), _v("C", "short", 0.5),
             _v("D", "no_position", 0.3)]
    s, direction = tally(votes, margin_threshold=T)
    assert direction == "long"
    assert abs(s.weighted_score - 1.2) < 1e-6                    # 0.8 + 0.4
    assert abs(s.margin - (1.2 - 0.5) / 2.0) < 1e-6              # gap / total cast (incl. no_position)
    assert not s.contested                                        # 0.35 >= 0.20


def test_dissent_summary_names_every_actual_dissenter():
    """R3 red test: a dissent_summary that drops a real dissenter fails."""
    votes = [_v("FUND-TECH", "long", 0.8), _v("BEAR-01", "short", 0.6),
             _v("SENT-01", "no_position", 0.4)]
    s, _ = tally(votes, margin_threshold=T)
    assert "BEAR-01" in s.dissent_summary and "short" in s.dissent_summary
    assert "SENT-01" in s.dissent_summary and "no_position" in s.dissent_summary
    assert "FUND-TECH" not in s.dissent_summary  # the winner is not a dissenter


def test_unanimous_ballot_reports_unanimous():
    s, _ = tally([_v("A", "long", 0.5), _v("B", "long", 0.5)], margin_threshold=T)
    assert s.dissent_summary == "unanimous" and not s.contested


def test_contested_below_threshold_and_boundary_at_exactly_020():
    """P5.3 + the R4 boundary rule: margin < 0.20 ⇒ CONTESTED; margin == 0.20 exactly ⇒ NOT."""
    # margin = (0.55 − 0.45) / 1.0 = 0.10 < 0.20 → contested
    c, _ = tally([_v("A", "long", 0.55), _v("B", "short", 0.45)], margin_threshold=T)
    assert c.contested
    # margin = (0.6 − 0.4) / 1.0 = 0.20 exactly → NOT contested (boundary pinned)
    e, _ = tally([_v("A", "long", 0.6), _v("B", "short", 0.4)], margin_threshold=T)
    assert abs(e.margin - 0.20) < 1e-9
    assert not e.contested


def test_tie_is_contested():
    s, _ = tally([_v("A", "long", 0.5), _v("B", "short", 0.5)], margin_threshold=T)
    assert s.contested and abs(s.margin) < 1e-9


def test_empty_ballot_fails_closed():
    with pytest.raises(ValueError, match="empty ballot"):
        tally([], margin_threshold=T)
