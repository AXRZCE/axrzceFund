"""The nine Phase-1 stub agents (replaced by real LLM agents in WP2).

Each returns a schema-valid but CLEARLY-FAKE artifact — deterministic canned content
so a WP1 cycle is reproducible with zero LLM calls. No agent here imports any LLM
SDK. The `_STUB` markers make it obvious in any output/log that this is not a real
memo, so a stub can never be mistaken for a real decision.
"""

from __future__ import annotations

from graphs.state import (
    Argument,
    Ballot,
    BallotSummary,
    Catalyst,
    DebateTurn,
    EntryPlan,
    KeyClaim,
    ResearchMemo,
    TradeProposal,
)

_STUB = "STUB — replaced in WP2"


# ── Research pool (P2) → ResearchMemo ───────────────────────────────────────────
class _StubResearcher:
    agent_id: str = "STUB"
    _stance = "long"
    _conviction = 0.5

    def run(self, candidate: str) -> ResearchMemo:
        return ResearchMemo(
            agent_id=self.agent_id, ticker=candidate, stance=self._stance,
            conviction=self._conviction, horizon_days=10, thesis=f"{_STUB}: {self.agent_id} thesis",
            key_claims=[KeyClaim(claim=f"{_STUB} claim", evidence=["stub_doc"], claim_type="inference")],
            catalysts=[Catalyst(event=f"{_STUB} catalyst", expected_window="2026-Q3")],
            invalidation_conditions=[f"{_STUB} invalidation"],
            risks=[f"{_STUB} risk"], what_would_change_my_mind=f"{_STUB}: new data")


class StubFUNDTECH(_StubResearcher):
    agent_id = "FUND-TECH"


class StubTECH01(_StubResearcher):
    agent_id = "TECH-01"
    _conviction = 0.55


class StubSENT01(_StubResearcher):
    agent_id = "SENT-01"
    _conviction = 0.45


# ── VERIF-01 (integrity service): validate/strip memos ──────────────────────────
class StubVERIF01:
    agent_id = "VERIF-01"

    def run(self, memos: list[ResearchMemo]) -> tuple[list[ResearchMemo], list[str]]:
        """Stub: passes all memos through, flags none. Real VERIF-01 (WP2) strips
        E4 claims and unfalsifiable theses."""
        return list(memos), []


# ── Adversarial pool (P4) → DebateTurn ──────────────────────────────────────────
class StubBULL01:
    agent_id = "BULL-01"

    def run(self, candidate: str, round_: int = 1) -> DebateTurn:
        return DebateTurn(
            agent_id=self.agent_id, round=round_, position="bull",
            arguments=[Argument(point=f"{_STUB} bull point", evidence=["stub_doc"], attacks=None)],
            concessions=[f"{_STUB} concession"], steelman_of_opponent=f"{_STUB} steelman")


class StubBEAR01:
    agent_id = "BEAR-01"

    def run(self, candidate: str, round_: int = 1) -> DebateTurn:
        return DebateTurn(
            agent_id=self.agent_id, round=round_, position="bear",
            arguments=[Argument(point=f"{_STUB} bear point", evidence=["stub_doc"], attacks="claim_0")],
            concessions=[f"{_STUB} concession"], steelman_of_opponent=f"{_STUB} steelman")


class StubMOD01:
    agent_id = "MOD-01"

    def run(self, turns: list[DebateTurn]) -> tuple[str, list[str]]:
        """Returns (debate_summary, premortem_top_risks)."""
        return f"{_STUB}: debate summary over {len(turns)} turns", [f"{_STUB} premortem risk"]


# ── Decision pool (P5/P6) → Ballot / TradeProposal ──────────────────────────────
class StubPM01:
    agent_id = "PM-01"

    def ballot(self, voters: list[str]) -> list[Ballot]:
        """Stub sealed ballot — each voter casts the same canned vote."""
        return [Ballot(voter=v, stance="long", conviction=0.5, size_inclination="standard")
                for v in voters]

    def propose(self, candidate: str, ballot_summary: BallotSummary,
                premortem: list[str]) -> TradeProposal:
        return TradeProposal(
            agent_id=self.agent_id, ticker=candidate, direction="long", size_pct_nav=1.0,
            entry_plan=EntryPlan(type="market_open", params={}), stop_loss="5pct",
            invalidation_conditions=[f"{_STUB} invalidation"], horizon_days=10,
            thesis=f"{_STUB}: PM thesis", premortem_top_risks=premortem,
            expected_edge_bps=25, ballot_summary=ballot_summary)


# ── Governance (P9): post-mortem ────────────────────────────────────────────────
class StubPMORT01:
    agent_id = "PMORT-01"

    def run(self, decision: dict) -> dict:
        """Stub post-mortem hook (real PMORT-01 runs after a closed trade, WP5)."""
        return {"agent_id": self.agent_id, "note": f"{_STUB}: post-mortem placeholder",
                "decision_ref": decision.get("cycle_id")}
