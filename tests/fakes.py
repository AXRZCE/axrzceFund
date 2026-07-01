"""Test doubles for the deep-loop (WP3 CP2).

The debate stubs left graphs/stubs/ when the real machinery (graphs/debate.py) landed — the
deep-loop debate node now takes an INJECTED implementation and fails closed without one. Tests
inject these doubles; they are test fixtures (allowed), not src canned-returns (banned outside
graphs/stubs/). Content is CLEARLY-FAKE-marked, deterministic, schema-valid.
"""

from __future__ import annotations

from graphs.state import (
    Argument,
    CycleState,
    DebateSummary,
    DebateTurn,
    FailureScenario,
    Premortem,
)

_FAKE = "FAKE (test double)"


def fake_debate_impl(state: CycleState) -> dict:
    """Deterministic, schema-valid debate result for skeleton tests (zero LLM)."""
    turns = [
        DebateTurn(
            agent_id="BULL-01", round=1, position="bull",
            arguments=[Argument(point=f"{_FAKE} bull point", evidence=["stub_doc"], attacks=None)],
            concessions=[f"{_FAKE} concession"], steelman_of_opponent=f"{_FAKE} steelman"),
        DebateTurn(
            agent_id="BEAR-01", round=1, position="bear",
            arguments=[Argument(point=f"{_FAKE} bear point", evidence=["stub_doc"],
                                attacks="claim_0")],
            concessions=[f"{_FAKE} concession"], steelman_of_opponent=f"{_FAKE} steelman"),
    ]
    summary = DebateSummary(
        resolved_points=[f"{_FAKE} resolved point"],
        unresolved_cruxes=[f"{_FAKE} crux"],
        premortem=Premortem(failure_scenarios=[FailureScenario(
            scenario=f"{_FAKE} failure scenario",
            early_warning_indicator=f"{_FAKE} observable indicator")]),
        process_flags=[],
    )
    return {
        "debate_turns": turns,
        "debate_summary": summary,
        "premortem_top_risks": [fs.scenario for fs in summary.premortem.failure_scenarios],
    }
