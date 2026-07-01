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
    EntryPlan,
    FailureScenario,
    Premortem,
    TradeProposal,
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


def fake_pm_impl(state: CycleState) -> dict:
    """Deterministic PM double (StubPM01 left at CP3). Grounded in the REAL tallied
    ballot_summary carried by the state — a fake that fabricated one would defeat the
    grounding the R5 tests protect."""
    proposal = TradeProposal(
        agent_id="PM-01", ticker=state.candidate or "TEST", direction="long", size_pct_nav=1.0,
        entry_plan=EntryPlan(type="market_open", params={}), stop_loss=f"{_FAKE} 5pct",
        invalidation_conditions=[f"{_FAKE} invalidation"], horizon_days=10,
        thesis=f"{_FAKE}: PM thesis", premortem_top_risks=list(state.premortem_top_risks),
        expected_edge_bps=90, ballot_summary=state.ballot_summary)
    return {"proposal": proposal}
