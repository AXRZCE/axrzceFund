"""Episodic capture + retrieval (WP5 R2/R3/R4) — the learning loop's CAPTURE-ONLY substrate.

memory-systems.md §1: **memory is a derived view; the append-only event log is the source of
truth.** This module captures post-mortems/lesson-candidates as events (ReplayTuple-stamped incl.
`manifest_version`), rebuilds the derived episodic store deterministically from the log (byte-equal,
tested), and retrieves by ticker/agent/date/tags for FUTURE consumption.

**The Phase-3 boundary (R3):** believability weighting is Phase 3. NO schema here carries any
weight/believability/multiplier field — `extra="forbid"` plus tests/test_learning.py's
forbidden-name scan enforce it; memory-systems §5.2's "no write API exists" is honored by not
building one. **Append-only (R3):** models are frozen; no update/delete surface exists.

**Isolation (R4, the shadow pattern):** this module imports NEITHER graphs.state NOR
graphs.deep_loop, and no live-decision module imports this one (AST-scanned both ways). The
memory-systems §3.2 context injection into P2/P6 is EXPLICITLY DEFERRED — Phase-1 captures and
retrieves; nothing feeds a live decision.

§3.1 deviation, recorded: the episode's `setup_fingerprint.embedding` (vector index) is deferred
to the WP6+ retrieval build; Phase-1 fingerprints are TAGS ONLY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

from core.config import load_config
from core.replay import ReplayTuple, new_trade_id

logger = structlog.get_logger()

DERIVED_STORE_PATH = Path("var/episodic_store.json")  # derived view — gitignored, rebuildable


# ── schemas (R2/R3; extra=forbid everywhere; frozen = append-only records) ─────────


class LessonCandidate(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    text: str
    generalizable: bool
    tags: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _max_50_words(cls, v: str) -> str:
        if len(v.split()) > 50:  # memory-systems §4.1: lessons are ≤50 words
            raise ValueError("lesson text exceeds 50 words (memory-systems §4.1)")
        return v


class KnowableAtDecisionTs(BaseModel):
    """§6.3 hindsight guard: 'was this knowable at decision_ts, citing only documents available
    then?' — the answer MUST carry citations into the decision record."""
    model_config = {"extra": "forbid", "frozen": True}
    answer: bool
    citations: list[str] = Field(min_length=1)


class PostMortem(BaseModel):
    """agent-specifications §6.3 post_mortem, with both guards as REQUIRED structure and the
    R6b interim flag. Grades 0–4; process and outcome are SEPARATE by construction (outcome-bias
    guard: 'a profitable trade with a refuted thesis is a loss that paid')."""
    model_config = {"extra": "forbid", "frozen": True}
    trade_id: str
    ticker: str
    outcome_vs_thesis: Literal["confirmed", "refuted", "unrelated_path"]
    luck_skill_assessment: str
    premortem_hit: bool
    process_grade: int = Field(ge=0, le=4)
    outcome_grade: int = Field(ge=0, le=4)
    knowable_at_decision_ts: KnowableAtDecisionTs
    observable_that_would_have_changed: str
    lesson: Optional[LessonCandidate] = None
    agent_grades: dict[str, str] = Field(default_factory=dict)
    interim: bool = False
    window_days: Optional[int] = None

    @field_validator("observable_that_would_have_changed")
    @classmethod
    def _observable_nonempty(cls, v: str) -> str:
        if not v.strip():  # the MOD-01 premortem pattern: unobservable = unfinished
            raise ValueError("observable_that_would_have_changed is empty — unfinished (R2)")
        return v

    @model_validator(mode="after")
    def _interim_rules(self) -> "PostMortem":
        if self.interim and self.window_days is None:
            raise ValueError("interim post-mortem must record window_days (R6b)")
        if self.interim and self.lesson is not None and self.lesson.generalizable:
            raise ValueError(
                "interim post-mortems may not emit generalizable lessons — a lesson from a "
                "partial window is an anecdote by construction (R6b)")
        return self


class Outcome(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    pnl_bps: float
    holding_days: int
    exit_reason: str            # stop | invalidation | horizon | no_trade | interim_mark
    mae_bps: float = 0.0
    mfe_bps: float = 0.0


class Episode(BaseModel):
    """memory-systems §3.1 (tags-only fingerprint in Phase 1; embedding deferred). Immutable."""
    model_config = {"extra": "forbid", "frozen": True}
    trade_id: str
    cycle_id: str
    ticker: str
    sector: str
    direction: str              # long | short | no_trade
    tags: list[str] = Field(default_factory=list)
    decision_record_ref: str    # the committed artifact / event ref this derives from
    outcome: Outcome
    premortem_hit: bool
    post_mortem_ref: str
    lesson_candidate: Optional[LessonCandidate] = None
    interim: bool = False
    window_days: Optional[int] = None


# ── capture (events are the source of truth; stamps carry manifest_version) ─────────


def capture_post_mortem(
    *,
    event_log: Any,
    post_mortem: PostMortem,
    episode: Episode,
    manifest: Any,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    agent_model_version: str,
) -> dict:
    """Append the post_mortem (+ lesson_candidate if present) and episode to the EVENT LOG.
    Returns the replay stamp. There is no update/delete counterpart — append-only by design."""
    rt = ReplayTuple(trade_id=post_mortem.trade_id or new_trade_id(), cycle_id=cycle_id,
                     decision_ts=decision_ts, agent_id="PMORT-01", prompt_version="wp5-pmort-v1",
                     model_version=agent_model_version, manifest_version=manifest.manifest_version,
                     config_version=load_config().config_version, code_version=code_version)
    stamp = rt.to_dict()
    event_log.append(event_type="post_mortem", cycle_id=cycle_id, agent_id="PMORT-01",
                     payload={"post_mortem": post_mortem.model_dump(),
                              "episode": episode.model_dump(), "replay_tuple": stamp})
    if post_mortem.lesson is not None:
        event_log.append(event_type="lesson_candidate", cycle_id=cycle_id, agent_id="PMORT-01",
                         payload={"lesson": post_mortem.lesson.model_dump(),
                                  "status": "probation",  # memory-systems §4.2 step 1
                                  "source_trade_id": post_mortem.trade_id, "replay_tuple": stamp})
    logger.info("post_mortem_captured", trade_id=post_mortem.trade_id,
                interim=post_mortem.interim, has_lesson=post_mortem.lesson is not None)
    return stamp


def capture_pmort_pending(*, event_log: Any, trade_id: str, cycle_id: str, reason: str) -> None:
    """R6c: the post-mortem could not run (model unavailable) — QUEUED, never skipped."""
    event_log.append(event_type="pmort_pending", cycle_id=cycle_id, agent_id="PMORT-01",
                     payload={"trade_id": trade_id, "reason": reason})
    logger.warning("pmort_pending", trade_id=trade_id, reason=reason)


def pending_post_mortems(event_log: Any) -> list[dict]:
    """Pending queue = pmort_pending events without a later post_mortem for the same trade_id.
    Read from the log (survives restart by construction)."""
    done = set()
    pending: dict[str, dict] = {}
    for e in event_log.get_events(agent_id="PMORT-01"):
        if e.event_type == "post_mortem":
            done.add(e.payload["post_mortem"]["trade_id"])
        elif e.event_type == "pmort_pending":
            pending[e.payload["trade_id"]] = e.payload
    return [p for tid, p in sorted(pending.items()) if tid not in done]


# ── derived store: deterministic rebuild from the log (byte-equal, tested) ──────────


def rebuild_episodic_store(event_log: Any, out_path: Path = DERIVED_STORE_PATH) -> bytes:
    """Rebuild the derived episodic view from the event log. DETERMINISTIC: sorted by
    (trade_id, cycle_id), canonical JSON — rebuilding twice is byte-equal; corruption of the
    derived file is always recoverable (memory-systems §1)."""
    episodes = []
    for e in event_log.get_events(agent_id="PMORT-01"):
        if e.event_type == "post_mortem":
            episodes.append(e.payload["episode"])
    episodes.sort(key=lambda ep: (ep["trade_id"], ep["cycle_id"]))
    blob = json.dumps({"episodes": episodes}, sort_keys=True, indent=1).encode()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return blob


# ── retrieval (R4): by ticker/agent/date/tags — consumed by NOTHING live in Phase 1 ──


def retrieve(
    episodes: list[dict],
    *,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    tags: Optional[list[str]] = None,
    date_from: Optional[str] = None,   # compares against cycle_id-embedded/decision dates upstream
    date_to: Optional[str] = None,
    trade_id: Optional[str] = None,
) -> list[dict]:
    """Filter the rebuilt store. Pure; deterministic order (trade_id)."""
    out = []
    for ep in episodes:
        if ticker and ep.get("ticker") != ticker:
            continue
        if direction and ep.get("direction") != direction:
            continue
        if trade_id and ep.get("trade_id") != trade_id:
            continue
        if tags and not set(tags) & set(ep.get("tags", [])):
            continue
        cyc = ep.get("cycle_id", "")
        if date_from and cyc and cyc < date_from:
            continue
        if date_to and cyc and cyc > date_to:
            continue
        out.append(ep)
    return sorted(out, key=lambda ep: ep.get("trade_id", ""))
