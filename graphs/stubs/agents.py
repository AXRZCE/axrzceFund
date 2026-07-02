"""The remaining Phase-1 stub agents (each leaves this package as its real agent lands).

Each returns a schema-valid but CLEARLY-FAKE artifact — deterministic canned content
so a skeleton cycle is reproducible with zero LLM calls. No agent here imports any LLM
SDK. The `_STUB` markers make it obvious in any output/log that this is not a real
memo, so a stub can never be mistaken for a real decision.

WP3 CP2 (R2): StubBULL01 / StubBEAR01 / StubMOD01 are REMOVED — the debate roles left the
quarantine when graphs/debate.py landed (anti-hoax: no canned returns outside stubs, and no
stub left behind for a role that has a real implementation). The deep-loop debate node now takes
an injected implementation; tests inject test doubles from tests/, production injects the real
graphs.debate machinery. StubPM01 no longer casts ballots (P5: PM-01 does not vote — a WP1
modeling error fixed here); the skeleton's sealed votes come from StubVoters.
"""

from __future__ import annotations

from graphs.state import (
    Ballot,
    Catalyst,
    KeyClaim,
    ResearchMemo,
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


# ── P5 sealed votes (skeleton only; real casting = graphs/debate.cast_votes, WP3 CP2) ──
class StubVoters:
    """Deterministic MIXED sealed votes so the REAL tally (graphs/ballot.tally) is exercised with
    texture, not unanimity. Voter roster per P5: research agents with valid memos + BULL-01/BEAR-01
    (stances constitutionally fixed to their roles); MOD-01/PM-01/governance do not vote."""

    agent_id = "P5-VOTERS"

    def cast(self) -> list[Ballot]:
        return [
            Ballot(voter="FUND-TECH", stance="long", conviction=0.6, size_inclination="standard"),
            Ballot(voter="TECH-01", stance="long", conviction=0.55, size_inclination="standard"),
            Ballot(voter="SENT-01", stance="no_position", conviction=0.4, size_inclination="small"),
            Ballot(voter="BULL-01", stance="long", conviction=0.8, size_inclination="standard"),
            Ballot(voter="BEAR-01", stance="short", conviction=0.6, size_inclination="small"),
        ]


# ── Decision pool (P6): StubPM01 REMOVED at WP3 CP3 — PM-01 is real (graphs/pm.py). ──
# The deep-loop pm node takes an injected implementation (tests inject a double), same
# pattern as the debate node at CP2. No stub left behind for a role with a real agent.


# ── Governance (P9): post-mortem ────────────────────────────────────────────────
class StubPMORT01:
    agent_id = "PMORT-01"

    def run(self, decision: dict) -> dict:
        """Stub post-mortem hook (real PMORT-01 runs after a closed trade, WP5)."""
        return {"agent_id": self.agent_id, "note": f"{_STUB}: post-mortem placeholder",
                "decision_ref": decision.get("cycle_id")}
