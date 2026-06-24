"""Deep-loop graph state = the decision record (WP1 ruling R1).

The memo models mirror agent-specifications.md §2 field-for-field; `CycleState`
aggregates them plus loop-orchestration bookkeeping (candidate, control flags,
per-stage outputs). Nothing here is invented memo content — where a field exists,
it is the spec's field. The state is a pydantic model so it serializes cleanly into
the checkpointer and the replay compare.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Optional

from pydantic import BaseModel, Field

Stance = Literal["long", "short", "neutral", "avoid"]
Direction = Literal["long", "short"]
ClaimType = Literal["fact", "inference", "estimate"]


# ── §2.1 ResearchMemo ───────────────────────────────────────────────────────────
class KeyClaim(BaseModel):
    claim: str
    evidence: list[str] = Field(default_factory=list)  # doc_ids
    claim_type: ClaimType


class Catalyst(BaseModel):
    event: str
    expected_window: str  # date-range


class ResearchMemo(BaseModel):
    agent_id: str
    ticker: str  # or "MARKET" for macro
    stance: Stance
    conviction: float = Field(ge=0.0, le=1.0)
    horizon_days: int
    thesis: str
    key_claims: list[KeyClaim] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    what_would_change_my_mind: str


# ── §2.2 DebateTurn ─────────────────────────────────────────────────────────────
class Argument(BaseModel):
    point: str
    evidence: list[str] = Field(default_factory=list)
    attacks: Optional[str] = None  # memo_claim_ref | null


class DebateTurn(BaseModel):
    agent_id: str
    round: int
    position: Literal["bull", "bear"]
    arguments: list[Argument] = Field(default_factory=list)
    concessions: list[str] = Field(default_factory=list)
    steelman_of_opponent: str


# ── §2.3 TradeProposal ──────────────────────────────────────────────────────────
class EntryPlan(BaseModel):
    type: Literal["market_open", "limit", "vwap_window"]
    params: dict[str, Any] = Field(default_factory=dict)


class BallotSummary(BaseModel):
    weighted_score: float
    margin: float = 0.0
    dissent_summary: str = ""
    contested: bool = False


class TradeProposal(BaseModel):
    agent_id: str
    ticker: str
    direction: Direction
    size_pct_nav: float
    entry_plan: EntryPlan
    stop_loss: str  # price | pct, as text
    invalidation_conditions: list[str] = Field(default_factory=list)
    horizon_days: int
    thesis: str
    premortem_top_risks: list[str] = Field(default_factory=list)
    expected_edge_bps: int
    ballot_summary: BallotSummary


# ── P5 sealed ballot ────────────────────────────────────────────────────────────
class Ballot(BaseModel):
    voter: str
    stance: Literal["long", "short", "no_position"]
    conviction: float = Field(ge=0.0, le=1.0)
    size_inclination: Literal["small", "standard", "high"]


# ── The full cycle state (the decision record) ──────────────────────────────────
class CycleState(BaseModel):
    """One deep-loop cycle's complete decision record. Carries the cycle-level replay
    identity; per-artifact ReplayTuples are stamped on the events emitted to the log.
    """

    model_config = {"validate_assignment": True}

    # identity / replay (cycle level)
    cycle_id: str
    decision_ts: str
    config_version: str
    code_version: str
    candidate: Optional[str] = None  # P1 screening

    # stage outputs (filled as the graph advances, protocol order)
    research_memos: list[ResearchMemo] = Field(default_factory=list)   # P2
    verified_memos: list[ResearchMemo] = Field(default_factory=list)   # VERIF-01
    verifier_flags: list[str] = Field(default_factory=list)
    debate_eligible: bool = False                                      # P3
    debate_turns: list[DebateTurn] = Field(default_factory=list)       # P4
    debate_summary: Optional[str] = None                              # MOD-01
    premortem_top_risks: list[str] = Field(default_factory=list)
    ballot: list[Ballot] = Field(default_factory=list)                 # P5 (sealed)
    ballot_summary: Optional[BallotSummary] = None
    proposal: Optional[TradeProposal] = None                          # P6 PM
    risk_gate_passed: Optional[bool] = None                           # P7 code gate
    risk_gate_reason: Optional[str] = None
    decision: Optional[dict[str, Any]] = None    # terminal intended-order/decision payload
    post_mortem: Optional[dict[str, Any]] = None  # P9 PMORT-01 (post-close hook)

    # control / orchestration (not memo content)
    completed_nodes: list[str] = Field(default_factory=list)
    halted: bool = False
    halt_reason: Optional[str] = None
    failure: Optional[dict[str, Any]] = None  # {node, error} on fail-closed

    # Fields excluded from the replay-equality compare (ruling R2): per-run identity.
    # trade_id is per-run identity too — it is nested in the `decision` payload, so it
    # is stripped there (not a top-level field).
    REPLAY_IDENTITY_FIELDS: ClassVar[tuple[str, ...]] = ("cycle_id", "decision_ts")

    def replay_comparable(self) -> dict[str, Any]:
        """The decision content used for the replay-determinism compare — everything
        except the per-run identity fields (ruling R2): top-level cycle_id/decision_ts
        and the trade_id embedded in the decision payload."""
        data = self.model_dump(exclude=set(self.REPLAY_IDENTITY_FIELDS))
        if isinstance(data.get("decision"), dict):
            data["decision"] = {k: v for k, v in data["decision"].items() if k != "trade_id"}
        return data
