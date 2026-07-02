"""P4 adversarial debate — BULL-01 vs BEAR-01 with MOD-01 adjudication (WP3 CP2, ruling R2).

Real machinery replacing the WP1 debate stubs. Structure per decision-protocols.md P4 +
agent-specifications.md §4: bull thesis → bear rebuttal → bounded rounds (`max_debate_rounds`,
configuration.md §4) → MOD-01 neutral `debate_summary` + pre-mortem with OBSERVABLE early-warning
indicators. The integrity properties are enforced by CODE in this module, not by prompt politeness:

  - **Heterogeneity at entry** (Frozen-Set §9.4): `family(BULL) ≠ family(BEAR)` via
    core.heterogeneity.assert_distinct_debaters — fail-closed before any call.
  - **Runtime scope**: roles resolve via `Manifest.resolve_runtime` — a CP1 validation-only role
    can never be seated here.
  - **Isolation** (P2/P4): a debater's context is ONLY the post-VERIF verified memos + the
    opponent's prior turns — enforced by this module's context assembly.
  - **Grounding**: every argument's `evidence` doc_ids ⊆ the doc_ids cited by the verified memos;
    an out-of-set citation raises `DebateGroundingError`.
  - **Round cap**: a turn beyond `max_debate_rounds` raises `DebateRoundCapError`.
  - **Capitulation / divergence** (P4.2): a BEAR that flips position, echoes the BULL's arguments,
    argues without ever attacking, or concedes in its closing VOIDS the debate (`DebateVoided`).
    (Symmetric for the BULL.) VERIF-01-as-judge adds semantic scoring at R6 (CP4).
  - **MOD neutrality** (§4.2): the summary schema (`graphs.state.DebateSummary`, extra=forbid) has
    NO stance field — a moderator output smuggling one fails validation; a pre-mortem scenario
    without an observable early-warning indicator is rejected as unfinished.

deep_loop NEVER imports this module (the debate node takes an injected implementation), so the
WP1 zero-LLM skeleton guarantee is preserved; production wiring injects `make_debate_node(...)`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import structlog
from pydantic import ValidationError

from core.config import load_config, param_number
from core.heterogeneity import assert_distinct_debaters
from core.llm import OpenRouterClient
from core.manifest import Manifest, ModelSpec
from core.replay import ReplayTuple, new_trade_id
from graphs.state import Ballot, ClosingStatement, DebateSummary, DebateTurn

logger = structlog.get_logger()

BULL_ROLE, BEAR_ROLE, MOD_ROLE = "BULL-01", "BEAR-01", "MOD-01"
ECHO_JACCARD = 0.8  # near-duplicate argument text across sides = echoing, not opposing


class DebateError(Exception):
    """Base: the debate could not produce a valid, integrity-checked result (fail-closed)."""


class DebateVoided(DebateError):
    """P4.2 role violation — capitulation/sycophancy: a debater abandoned its assigned side."""


class DebateGroundingError(DebateError):
    """An argument cited a doc_id outside the verified-memo evidence set."""


class DebateRoundCapError(DebateError):
    """More rounds than `max_debate_rounds` — the cap may never be extended (P4.1)."""


# ── pure code checks (zero-spend; the red tests exercise these directly) ─────────


def allowed_doc_ids(verified_memos: Iterable[dict]) -> set[str]:
    """The grounding universe: every doc_id cited in the post-VERIF memos' key_claims."""
    allowed: set[str] = set()
    for memo in verified_memos:
        for kc in memo.get("key_claims", []):
            allowed.update(kc.get("evidence", []))
    return allowed


def check_grounding(turns: Iterable[DebateTurn], allowed: set[str]) -> None:
    """Every argument's evidence must stay inside the verified-memo doc_id set (P4.2 rule 1)."""
    for t in turns:
        for arg in t.arguments:
            stray = [d for d in arg.evidence if d not in allowed]
            if stray:
                raise DebateGroundingError(
                    f"{t.agent_id} round {t.round} cites doc_id(s) {stray} outside the verified-memo "
                    f"evidence set — uncited/invented evidence voids the argument (fail-closed)."
                )


def check_round_cap(turns: Iterable[DebateTurn], max_rounds: int) -> None:
    """P4.1: MOD-01 may end a debate early but may NEVER extend past the cap."""
    over = [t for t in turns if t.round > max_rounds]
    if over:
        raise DebateRoundCapError(
            f"turn(s) beyond max_debate_rounds={max_rounds}: "
            f"{[(t.agent_id, t.round) for t in over]} — the round cap may never be extended."
        )


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def check_capitulation(
    turns: list[DebateTurn], closings: list[ClosingStatement]
) -> None:
    """P4.2 capitulation rule, code-checkable form. VOIDS the debate when a debater:
      1. emits a turn whose `position` is not its assigned side (flip);
      2. echoes the opponent (an argument point near-duplicating an opposing point);
      3. (BEAR) never attacks anything across the whole debate — a bear that doesn't attack
         is agreeing by omission;
      4. closes on the opposite side (closing.position != assigned side) or with empty points.
    Concessions on individual points are allowed (encouraged from round 2); abandoning the
    assigned side is not.
    """
    assigned = {"BULL-01": "bull", "BEAR-01": "bear"}
    for t in turns:
        want = assigned.get(t.agent_id)
        if want and t.position != want:
            raise DebateVoided(
                f"{t.agent_id} argued position {t.position!r} in round {t.round} — role flip "
                f"(assigned {want!r}); capitulation voids the debate (P4.2)."
            )
        if not t.arguments:
            raise DebateVoided(
                f"{t.agent_id} round {t.round} has no arguments — an empty turn is capitulation."
            )

    bull_points = [a.point for t in turns if t.position == "bull" for a in t.arguments]
    bear_points = [a.point for t in turns if t.position == "bear" for a in t.arguments]
    for bp in bear_points:
        for lp in bull_points:
            if _jaccard(bp, lp) >= ECHO_JACCARD:
                raise DebateVoided(
                    f"BEAR argument echoes a BULL argument (jaccard>= {ECHO_JACCARD}): "
                    f"{bp[:80]!r} ~ {lp[:80]!r} — a bear that repeats the bull is not opposing it."
                )

    bear_attacks = [a for t in turns if t.position == "bear" for a in t.arguments if a.attacks]
    if turns and not bear_attacks:
        raise DebateVoided(
            "BEAR made zero attack references across the debate — agreeing by omission (P4.2: "
            "every argument must cite evidence or attack a specific claim by reference)."
        )

    for c in closings:
        want = assigned.get(c.agent_id)
        if want and c.position != want:
            raise DebateVoided(
                f"{c.agent_id} closing declares position {c.position!r} (assigned {want!r}) — "
                f"closing statements must argue the assigned side at full strength (P4.2)."
            )
        if not any(p.strip() for p in c.strongest_points):
            raise DebateVoided(f"{c.agent_id} closing has no substantive points — capitulation.")


def check_mod_neutrality(raw: dict) -> DebateSummary:
    """Validate MOD-01 output. `DebateSummary` is extra=forbid with NO stance field, so a stance/
    direction/winner key fails pydantic validation (the §4.2 neutrality guard). A pre-mortem
    scenario without an observable early-warning indicator is unfinished → rejected."""
    summary = DebateSummary.model_validate(raw)  # ValidationError on any smuggled stance field
    for fs in summary.premortem.failure_scenarios:
        if not fs.early_warning_indicator.strip():
            raise DebateError(
                f"pre-mortem scenario {fs.scenario[:60]!r} has no observable early-warning "
                f"indicator — '.. without observable early-warning indicators is unfinished' (§4.2)."
            )
    return summary


def preflight(manifest: Manifest) -> tuple[ModelSpec, ModelSpec, ModelSpec]:
    """Resolve the debate roster on the RUNTIME path and enforce heterogeneity at entry
    (fail-closed BEFORE any spend). Pure — testable with a constructed manifest."""
    bull = manifest.resolve_runtime(BULL_ROLE)
    bear = manifest.resolve_runtime(BEAR_ROLE)
    mod = manifest.resolve_runtime(MOD_ROLE)
    assert_distinct_debaters(bull.family, bear.family)
    return bull, bear, mod


# ── LLM runner ────────────────────────────────────────────────────────────────────

_TURN_SCHEMA = (
    '{"round": int, "position": "bull"|"bear", '
    '"arguments": [{"point": str, "evidence": [doc_id from the memos], '
    '"attacks": "<quoted opposing/memo claim>"|null}], '
    '"concessions": [str], "steelman_of_opponent": str}'
)
_CLOSING_SCHEMA = (
    '{"position": "bull"|"bear", "strongest_points": [str, str, str], "conviction": 0.0-1.0}'
)

_BULL_SYS = (
    "You are BULL-01, the fund's adversarial bull. Construct the strongest HONEST case FOR the "
    "candidate, attacking the bear's and the memos' weak claims by reference. You are structurally "
    "forbidden from agreeing with the bear's stance: concede individual points when they are right "
    "(concessions non-empty from round 2), but your closing argues the bull side at full strength. "
    "Every argument must cite doc_ids that appear in the verified memos — numbers you cannot cite "
    "do not exist. Output ONLY JSON."
)
_BEAR_SYS = (
    "You are BEAR-01, the fund's immune system. You cannot capitulate. If the long case is strong, "
    "find the price, scenario, or crowding condition under which it still fails — there always is "
    "one. Attack specific memo/bull claims by reference. Concede individual points when they are "
    "right (concessions non-empty from round 2), but your closing argues the bear side at full "
    "strength. Every argument must cite doc_ids that appear in the verified memos. Output ONLY JSON."
)
_MOD_SYS = (
    "You are MOD-01, the debate moderator. You have NO view on the stock and never will — no "
    "stance, no direction, no winner. Your product is the map of the disagreement: resolved points, "
    "unresolved cruxes, and a pre-mortem whose every failure scenario carries an OBSERVABLE "
    "early-warning indicator. Output ONLY JSON: "
    '{"resolved_points": [str], "unresolved_cruxes": [str], '
    '"premortem": {"failure_scenarios": [{"scenario": str, "early_warning_indicator": str}]}, '
    '"process_flags": [str]}'
)
_VOTE_SYS = (
    "You are casting a SEALED ballot on the candidate after reading the verified memos and the "
    "moderator's debate summary. No other voter sees your ballot. Output ONLY JSON: "
    '{"stance": "long"|"short"|"no_position", "conviction": 0.0-1.0, '
    '"size_inclination": "small"|"standard"|"high"}'
)


@dataclass
class DebateResult:
    candidate: str
    turns: list[DebateTurn]
    closings: list[ClosingStatement]
    summary: DebateSummary
    premortem_top_risks: list[str]
    stamps: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0


def _extract_json(text: str) -> dict:
    s = text.find("{")
    if s == -1:
        raise ValueError(f"no JSON object in reply: {text[:120]!r}")
    obj, _ = json.JSONDecoder().raw_decode(text[s:])
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    return obj


class _Metered:
    """Per-debate metering + replay stamping (manifest_version included — WP3 R5)."""

    def __init__(self, client: OpenRouterClient, manifest: Manifest, cycle_id: str,
                 decision_ts: str, code_version: str):
        self.client, self.man = client, manifest
        self.cycle_id, self.decision_ts, self.code_version = cycle_id, decision_ts, code_version
        self.config_version = load_config().config_version
        self.stamps: list[dict] = []
        self.cost = 0.0

    def call(self, role: str, spec: ModelSpec, system: str, user: str, *, max_tokens: int) -> str:
        resp = self.client.call(
            model_version=spec.model_version, provider=spec.provider,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"}, max_tokens=max_tokens,
        )
        self.cost += resp.usage.cost_usd
        rt = ReplayTuple(
            trade_id=new_trade_id(), cycle_id=self.cycle_id, decision_ts=self.decision_ts,
            agent_id=role, prompt_version="cp2-debate-v1", model_version=resp.model_version,
            manifest_version=self.man.manifest_version, config_version=self.config_version,
            code_version=self.code_version,
        )
        self.stamps.append({**rt.to_dict(), "usage": {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "cost_usd": resp.usage.cost_usd}})
        if resp.finish_reason == "length":
            raise ValueError(f"{role} reply truncated at max_tokens={max_tokens}")
        return resp.text


def _memo_block(verified_memos: list[dict]) -> str:
    return "\n\n".join(
        f"--- VERIFIED MEMO {i + 1} ({m.get('agent_id', '?')}) ---\n{json.dumps(m)}"
        for i, m in enumerate(verified_memos)
    )


def _opponent_block(turns: list[DebateTurn], my_position: str) -> str:
    opp = [t for t in turns if t.position != my_position]
    if not opp:
        return "(no opponent turns yet — you open the debate)"
    return "\n\n".join(f"--- OPPONENT ROUND {t.round} ---\n{t.model_dump_json()}" for t in opp)


def _debater_turn(mx: _Metered, role: str, spec: ModelSpec, system: str, candidate: str,
                  verified_memos: list[dict], turns: list[DebateTurn], rnd: int,
                  want_closing: bool) -> tuple[DebateTurn, Optional[ClosingStatement]]:
    """One debater turn (isolation: memos + opponent turns ONLY), one P2-style retry."""
    position = "bull" if role == BULL_ROLE else "bear"
    closing_ask = (
        f'\nThis is the FINAL round. Your JSON must contain BOTH (a) ALL DebateTurn fields '
        f'(position, arguments, concessions, steelman_of_opponent — the closing round still '
        f'argues) AND (b) an ADDITIONAL top-level "closing" key: {_CLOSING_SCHEMA} arguing YOUR '
        f'side. A reply containing only "closing" is INVALID.'
        if want_closing else ""
    )
    user = (
        f"Candidate: {candidate}\nRound: {rnd} of the debate. Your side: {position}.\n\n"
        f"{_memo_block(verified_memos)}\n\n"
        f"OPPONENT'S PRIOR TURNS (your full visibility of the debate):\n"
        f"{_opponent_block(turns, position)}\n\n"
        f"Produce your DebateTurn as JSON: {_TURN_SCHEMA}{closing_ask}"
    )
    last: Exception | None = None
    for _attempt in range(2):
        try:
            # P2 pattern: ONE retry WITH ERROR FEEDBACK — the CP4 smoke showed a bare resend just
            # reproduces the same malformed reply (GLM round-3 emitted only "closing" twice).
            ask = user if last is None else (
                f"{user}\n\nYOUR PREVIOUS REPLY WAS INVALID: {str(last)[:300]}\n"
                f"Reply again with ALL required fields present.")
            raw = _extract_json(mx.call(role, spec, system, ask, max_tokens=4096))
            closing_raw = raw.pop("closing", None)
            raw.setdefault("agent_id", role)
            raw["round"] = rnd
            turn = DebateTurn.model_validate(raw)
            closing = None
            if want_closing:
                if closing_raw is None:
                    raise ValueError("final round must include a closing statement (§4.1)")
                closing_raw.setdefault("agent_id", role)
                closing = ClosingStatement.model_validate(closing_raw)
            return turn, closing
        except (ValueError, ValidationError) as e:  # parse/schema → one retry, then fail closed
            last = e
    raise DebateError(f"{role} failed to produce a valid round-{rnd} turn after retry: {last}")


def run_debate(
    *,
    candidate: str,
    verified_memos: list[dict],
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    max_rounds: Optional[int] = None,
) -> DebateResult:
    """Run one full P4 debate. Fail-closed at every integrity boundary; every call metered and
    replay-stamped (incl. manifest_version)."""
    if not verified_memos:
        raise DebateError("no verified memos — debaters read ONLY post-VERIF memos (P4 isolation)")
    bull, bear, mod = preflight(manifest)  # runtime scope + heterogeneity, before any spend
    rounds = int(max_rounds if max_rounds is not None else param_number("max_debate_rounds"))
    mx = _Metered(client, manifest, cycle_id, decision_ts, code_version)
    allowed = allowed_doc_ids(verified_memos)

    turns: list[DebateTurn] = []
    closings: list[ClosingStatement] = []
    for rnd in range(1, rounds + 1):
        final = rnd == rounds
        for role, spec, system in ((BULL_ROLE, bull, _BULL_SYS), (BEAR_ROLE, bear, _BEAR_SYS)):
            turn, closing = _debater_turn(
                mx, role, spec, system, candidate, verified_memos, turns, rnd, want_closing=final)
            turns.append(turn)
            if closing is not None:
                closings.append(closing)

    # integrity gates (code, not vibes) — any failure voids/fails the debate BEFORE MOD-01 runs
    check_round_cap(turns, rounds)
    check_grounding(turns, allowed)
    check_capitulation(turns, closings)

    transcript = "\n\n".join(t.model_dump_json() for t in turns)
    mod_user = (
        f"Candidate: {candidate}\n\n{_memo_block(verified_memos)}\n\n"
        f"--- FULL DEBATE TRANSCRIPT ({len(turns)} turns) ---\n{transcript}\n\n"
        f"Write the neutral debate_summary JSON."
    )
    last: Exception | None = None
    summary: Optional[DebateSummary] = None
    for _attempt in range(2):
        try:
            summary = check_mod_neutrality(_extract_json(
                mx.call(MOD_ROLE, mod, _MOD_SYS, mod_user, max_tokens=4096)))
            break
        except (ValueError, ValidationError, DebateError) as e:
            last = e
    if summary is None:
        raise DebateError(f"MOD-01 failed to produce a valid neutral summary after retry: {last}")

    logger.info("debate_complete", candidate=candidate, turns=len(turns),
                cruxes=len(summary.unresolved_cruxes), cost_usd=round(mx.cost, 6))
    return DebateResult(
        candidate=candidate, turns=turns, closings=closings, summary=summary,
        premortem_top_risks=[fs.scenario for fs in summary.premortem.failure_scenarios],
        stamps=mx.stamps, cost_usd=round(mx.cost, 6),
    )


def cast_votes(
    *,
    candidate: str,
    verified_memos: list[dict],
    result: DebateResult,
    research_voters: list[str],
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
) -> tuple[list[Ballot], list[dict], float]:
    """P5.1 sealed casting. Voters = research agents with valid memos + BULL-01/BEAR-01, whose
    stances are CONSTITUTIONALLY FIXED to their roles (code-enforced; an attempted flip is logged,
    not obeyed). Each vote is an independent call (sealed by construction); voters see the verified
    memos + the MOD summary — never another ballot. Returns (ballots, stamps, cost)."""
    mx = _Metered(client, manifest, cycle_id, decision_ts, code_version)
    context = (
        f"Candidate: {candidate}\n\n{_memo_block(verified_memos)}\n\n"
        f"--- MODERATOR DEBATE SUMMARY ---\n{result.summary.model_dump_json()}\n\n"
        f"Cast your sealed ballot JSON now."
    )
    fixed = {BULL_ROLE: "long", BEAR_ROLE: "short"}
    ballots: list[Ballot] = []
    for voter in [*research_voters, BULL_ROLE, BEAR_ROLE]:
        spec = manifest.resolve_runtime(voter)
        # the ballot JSON is tiny, but reasoning models burn completion tokens before emitting it —
        # give headroom and one retry (a truncated vote is a failed cast, never a silent default)
        last: Exception | None = None
        raw = None
        for _attempt in range(2):
            try:
                raw = _extract_json(mx.call(voter, spec, _VOTE_SYS, context, max_tokens=2048))
                break
            except ValueError as e:
                last = e
        if raw is None:
            raise DebateError(f"{voter} failed to cast a valid sealed ballot after retry: {last}")
        if voter in fixed and raw.get("stance") != fixed[voter]:
            logger.warning("vote_constitutional_override", voter=voter,
                           attempted=raw.get("stance"), fixed=fixed[voter])
            raw["stance"] = fixed[voter]  # constitutionally fixed to the role (P5)
        ballots.append(Ballot(voter=voter, **{k: raw[k] for k in
                                              ("stance", "conviction", "size_inclination")}))
    return ballots, mx.stamps, round(mx.cost, 6)
