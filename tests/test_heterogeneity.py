"""WP3 CP0 — heterogeneity invariant enforcement (shared primitive for R2 debate + R6 judge).

Anti-hoax: the decorrelation invariant (configuration.md §3 / Frozen-Set §9.4) is enforced in
CODE, fail-closed — not by a manifest comment. Delete the check in core/heterogeneity.py and a
same-family debate pair (or a same-family judge where a disjoint family exists) stops raising ->
these tests go RED.

Pure unit: no key, no network, no spend.
"""

from __future__ import annotations

import pytest

from core.heterogeneity import (
    HeterogeneityError,
    assert_distinct_debaters,
    assert_judge_disjoint,
    resolve_judge_family,
)

ROSTER = ["chinese", "openai", "google"]  # the ADR-2 three-family value roster


# ── R2: BULL vs BEAR must be different families ──────────────────────────────────
def test_distinct_debaters_ok():
    assert_distinct_debaters("chinese", "openai")  # returns None, no raise


def test_same_family_debaters_raises():
    with pytest.raises(HeterogeneityError, match="arguing with itself"):
        assert_distinct_debaters("google", "google")


# ── R6: judge family must differ from judged where an alternative exists ──────────
def test_judge_disjoint_ok():
    # OpenAI judging a Google agent, with the full roster available -> fine.
    assert_judge_disjoint("openai", "google", ROSTER)  # no raise


def test_same_family_judge_with_alternative_raises():
    # A Google judge on a Google agent while OpenAI/Chinese are available -> fail-closed.
    with pytest.raises(HeterogeneityError, match="required where an alternative exists"):
        assert_judge_disjoint("google", "google", ROSTER)


def test_judge_no_alternative_is_logged_not_raised():
    # Single-family roster: same-family judging is permitted but logged (never silent) -> no raise.
    assert_judge_disjoint("google", "google", ["google"])


# ── resolver the orchestrator uses at call time (R6) ─────────────────────────────
def test_resolve_picks_disjoint_deterministic():
    fam = resolve_judge_family("google", ROSTER)
    assert fam != "google"
    assert fam in {"chinese", "openai"}
    assert fam == resolve_judge_family("google", ROSTER)  # deterministic across calls
    # its own output must satisfy the disjointness assertion
    assert_judge_disjoint(fam, "google", ROSTER)


def test_resolve_no_alternative_returns_judged():
    assert resolve_judge_family("google", ["google"]) == "google"
