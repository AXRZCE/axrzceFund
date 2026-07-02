"""P5 sealed-ballot tally (WP3 CP2, ruling R3) — pure code, zero LLM.

Replaces the WP1 hardcoded `BallotSummary(0.5, 0.2, ...)` (the old deep_loop.py:135). The tally is
decision-protocols.md P5 step 2, with Phase 1–2 equal weights (configuration.md §4
`weighting_enabled = false` → w_i = 1 — weights without track records are noise):

    score(d)   = Σ_i  w_i · conviction_i · 1[stance_i = d]          (P5.2)
    margin     = (score_top − score_runner_up) / total_cast_weight   (config §4: "weighted-score
                 margin below 20% of TOTAL CAST WEIGHT = CONTESTED"; total cast weight =
                 Σ_i w_i · conviction_i over ALL ballots, no_position included — an abstaining
                 voter's weight dampens the margin rather than vanishing)
    contested  = margin < ballot_margin_threshold                    (P5.3; margin == threshold ⇒
                 NOT contested — the boundary rule pinned by WP3 R4's boundary test)
    weighted_score  = score(winning direction), raw
    dissent_summary = names the ACTUAL dissenters — every voter whose stance ≠ the winning
                      direction, with stance and conviction (P5 output; PM-01's override guard
                      reads this field, agent-specifications §5.1)

The winning DIRECTION is not a BallotSummary field (the four-field shape is frozen per the WP1-R1
reconcile); `tally` returns it alongside. MOD-01 / PM-01 / governance agents do not vote (P5).
"""

from __future__ import annotations

from typing import Literal, Optional

from graphs.state import Ballot, BallotSummary

Direction = Literal["long", "short", "no_position"]


def tally(
    votes: list[Ballot],
    *,
    margin_threshold: float,
    weights: Optional[dict[str, float]] = None,
) -> tuple[BallotSummary, str]:
    """Unseal + tally (P5.2/P5.3). Returns (BallotSummary, winning_direction).

    `weights` defaults to w_i = 1 for every voter (Phase 1–2, weighting_enabled=false). Fail-closed
    on an empty ballot — a candidate with no votes must never reach a summary.
    """
    if not votes:
        raise ValueError("empty ballot: no sealed votes to tally (fail-closed)")
    w = weights or {}

    def wt(v: Ballot) -> float:
        return w.get(v.voter, 1.0) * v.conviction

    scores: dict[str, float] = {"long": 0.0, "short": 0.0, "no_position": 0.0}
    for v in votes:
        scores[v.stance] += wt(v)

    total_cast = sum(wt(v) for v in votes)
    # winner among the tradeable directions; no_position weight counts in total_cast only
    directional = {d: scores[d] for d in ("long", "short")}
    winner = max(directional, key=lambda d: directional[d])
    runner_up = min(directional, key=lambda d: directional[d])
    margin = ((directional[winner] - directional[runner_up]) / total_cast) if total_cast > 0 else 0.0
    # Boundary rule (P5.3 / WP3 R4): margin == threshold ⇒ NOT contested. Compare on a rounded
    # margin so float noise can't flip the boundary (0.6−0.4 = 0.19999999999999998 must count as
    # exactly 0.20, not "below threshold") — caught by the committed boundary test.
    contested = round(margin, 9) < margin_threshold

    dissenters = [v for v in votes if v.stance != winner]
    dissent_summary = (
        "; ".join(f"{v.voter} voted {v.stance} (conviction {v.conviction:.2f})" for v in dissenters)
        if dissenters else "unanimous"
    )

    summary = BallotSummary(
        weighted_score=round(directional[winner], 6),
        margin=round(margin, 6),
        dissent_summary=dissent_summary,
        contested=contested,
    )
    return summary, winner
