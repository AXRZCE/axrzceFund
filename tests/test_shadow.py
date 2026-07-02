"""WP3 CP4 red tests — R7 shadow-ensemble. Pure code, zero LLM.

Gut map: add a CycleState/TradeProposal import (the only channel to the live decision) →
structural-isolation test red; tolerate an empty shadow log in compute_decorrelation →
nothing-to-measure test red; hardcode the metric → distinctness test red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphs.shadow import ShadowVote, compute_decorrelation

SHADOW_SRC = Path("graphs/shadow.py")


def _sv(role, family, stance, conviction=0.5):
    return ShadowVote(role=role, family=family, model_version="m", stance=stance,
                      conviction=conviction, stamp={})


# ── R7: isolation is STRUCTURAL — the shadow module cannot touch the live decision ──
def test_shadow_module_structurally_isolated_from_live_state():
    """graphs/shadow.py must IMPORT neither graphs.state (CycleState/TradeProposal live there) nor
    graphs.deep_loop — with no import there is no code path by which a shadow output can mutate
    the live decision. AST-scanned (docstrings don't count). Add such an import (the gut) → red."""
    import ast

    tree = ast.parse(SHADOW_SRC.read_text(encoding="utf-8"))
    offending = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                ("graphs.state", "graphs.deep_loop")):
            offending.append(f"from {node.module} import ...")
        if isinstance(node, ast.Import):
            offending += [a.name for a in node.names
                          if a.name.startswith(("graphs.state", "graphs.deep_loop"))]
    assert not offending, (
        f"graphs/shadow.py imports live-state modules {offending} — the shadow path must have no "
        f"write access to live decision state (R7 isolation)"
    )


def test_shadow_vote_records_are_frozen():
    v = _sv("BULL-01-CAND-DEEPSEEK", "chinese", "long")
    with pytest.raises(Exception):  # dataclass(frozen=True)
        v.stance = "short"  # type: ignore[misc]


# ── R7: decorrelation is measured from the LOGGED votes ─────────────────────────────
def test_empty_shadow_log_cannot_be_measured():
    """R7 red test: remove the shadow logging and there is NOTHING to measure — fail-closed,
    never a fabricated metric."""
    with pytest.raises(ValueError, match="no shadow votes logged"):
        compute_decorrelation({"BULL-01(chinese)": "long"}, [])


def test_metric_computed_from_votes_known_case():
    """live A=long, B=short; one shadow long → pairs: (A,B) no, (A,S) yes, (B,S) no → 1/3."""
    live = {"BULL-01(chinese)": "long", "BEAR-01(openai)": "short"}
    shadows = [_sv("BULL-01-BASELINE-WEST", "google", "long")]
    m = compute_decorrelation(live, shadows)
    assert m["n_voters"] == 3 and m["n_pairs"] == 3
    assert abs(m["stance_agreement_rate"] - 1 / 3) < 1e-4  # metric rounds to 4 decimals


def test_distinct_vote_sets_yield_distinct_metrics():
    """Gut-detector: hardcode the metric and two different logs return the same number → red."""
    live = {"BULL-01(chinese)": "long", "BEAR-01(openai)": "short"}
    a = compute_decorrelation(live, [_sv("X", "google", "long")])
    b = compute_decorrelation(live, [_sv("X", "google", "no_position")])
    assert a["stance_agreement_rate"] != b["stance_agreement_rate"]
