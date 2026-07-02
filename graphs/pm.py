"""P6 PM synthesis & proposal — PM-01 (WP3 CP3, rulings R4 + R5).

PM-01 (T2_C Google, third family) consumes the verified memos + MOD-01 debate_summary +
the COMPUTED ballot_summary and emits the §2.3 TradeProposal or an explicit no_trade.

Division of labor (the TECH-01 pattern): **the model owns judgment, code owns arithmetic.**
The LLM supplies direction/conviction/thesis/stop/invalidation/horizon/edge; the SIZE is
SERVER-AUTHORITATIVE — computed by `size_position` below and written over whatever the model
says. P6 discipline enforced in code, not prompt-trusted:

  - `base_size_pct_nav = 1.0%` × conviction_factor (0.5×–1.5×, linear in conviction) — config §5.
  - Haircuts multiplicative, DOWNWARD ONLY (config §5): contested ×0.5, regime_mismatch ×0.7,
    unresolved_bear_crux ×0.7, liquidity_thin ×0.8. Phase-1 wiring: `contested` from the tally
    (R4) and `unresolved_bear_crux` from MOD-01's unresolved_cruxes; regime/liquidity flags exist
    but default False until their data sources land (Macro memo = Phase 2, liquidity = WP4).
  - Hard caps AFTER the haircuts: contested ⇒ `contested_size_cap_pct_nav = 0.5%` (R4: both the
    haircut AND the cap fire); DEBATE_FAILED ⇒ `undebated_size_cap_pct_nav = 0.75%`; all new
    positions ⇒ `max_new_position_pct_nav = 2.5%`.
  - `expected_edge_bps ≥ edge_to_cost_multiple × round-trip cost` validity check. ⚠️ Phase-1
    placeholder cost (`ASSUMED_ROUND_TRIP_COST_BPS`) until the backtesting-framework cost model
    lands — FLAGGED in the CP3 readout, not hidden.
  - Override guard (agent-specifications §5.1 / P6.3): proposing AGAINST the ballot direction
    requires a written rebuttal addressing the majority's strongest crux, and overrides are capped
    at `max_overrides_per_month = 2` (the caller supplies the month's prior count; the event log
    records `pm_override` events as the durable tally).

R5 replay: the PM decision is stored in the event log (`proposal_written` / `no_trade`), and
`reconstruct_decision` reads it back WITHOUT any LLM client — replay reads the stored decision,
it never re-calls the model. Stamps carry manifest_version (WP3 R5 / CP0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from core.config import load_config, param_number
from core.llm import OpenRouterClient
from core.manifest import Manifest
from core.replay import ReplayTuple, new_trade_id
from graphs.state import BallotSummary, DebateSummary, EntryPlan, TradeProposal

logger = structlog.get_logger()

PM_ROLE = "PM-01"

BASE_SIZE_PCT_NAV = param_number("base_size_pct_nav")                    # 1.0
CONTESTED_CAP_PCT_NAV = param_number("contested_size_cap_pct_nav")       # 0.5
UNDEBATED_CAP_PCT_NAV = param_number("undebated_size_cap_pct_nav")       # 0.75
MAX_NEW_POSITION_PCT_NAV = param_number("max_new_position_pct_nav")      # 2.5
EDGE_TO_COST_MULTIPLE = param_number("edge_to_cost_multiple")            # 3
MAX_OVERRIDES_PER_MONTH = int(param_number("max_overrides_per_month"))   # 2

# configuration.md §5 haircut table (multiplicative, downward only). The ×-literals defeat the
# param parser, so they live here; tests/test_pm.py guards that the doc still carries them.
HAIRCUTS = {
    "contested": 0.5,
    "regime_mismatch": 0.7,
    "unresolved_bear_crux": 0.7,
    "liquidity_thin": 0.8,
}

# ⚠️ Phase-1 placeholder until the cost model lands (backtesting-framework / WP4): a conservative
# round-trip cost for liquid S&P-500 names. The edge check is real; this constant is the flagged
# stand-in for its second input.
ASSUMED_ROUND_TRIP_COST_BPS = 20.0


class PMError(Exception):
    """PM-01 produced an invalid/ungrounded decision (fail-closed)."""


class OverrideError(PMError):
    """Override against the ballot without a rebuttal, or past the monthly cap (P6.3)."""


class EdgeError(PMError):
    """expected_edge_bps below edge_to_cost_multiple × round-trip cost (P6.3)."""


# ── pure sizing arithmetic (server-authoritative; the red tests exercise these) ──


def conviction_factor(conviction: float) -> float:
    """config §5: conviction modulates 0.5×–1.5× of base, linear in conviction ∈ [0,1]."""
    return 0.5 + max(0.0, min(1.0, conviction))


def size_position(
    *,
    conviction: float,
    contested: bool,
    debate_failed: bool = False,
    regime_mismatch: bool = False,
    unresolved_bear_crux: bool = False,
    liquidity_thin: bool = False,
) -> tuple[float, dict[str, Any]]:
    """P6.4 sizing: base × conviction_factor, then each applicable haircut multiplies DOWNWARD,
    then the hard caps bind. Sizing never increases through narrative enthusiasm. Returns
    (size_pct_nav, audit) where audit records every factor/cap applied — the arithmetic is
    reproducible from the audit alone."""
    cf = conviction_factor(conviction)
    size = BASE_SIZE_PCT_NAV * cf
    audit: dict[str, Any] = {"base": BASE_SIZE_PCT_NAV, "conviction_factor": round(cf, 4),
                             "haircuts": {}, "caps": {}}
    flags = {
        "contested": contested,
        "regime_mismatch": regime_mismatch,
        "unresolved_bear_crux": unresolved_bear_crux,
        "liquidity_thin": liquidity_thin,
    }
    for name, on in flags.items():
        if on:
            size *= HAIRCUTS[name]
            audit["haircuts"][name] = HAIRCUTS[name]

    if contested and size > CONTESTED_CAP_PCT_NAV:      # R4: the cap binds AFTER the haircut
        audit["caps"]["contested_size_cap_pct_nav"] = CONTESTED_CAP_PCT_NAV
        size = CONTESTED_CAP_PCT_NAV
    if debate_failed and size > UNDEBATED_CAP_PCT_NAV:
        audit["caps"]["undebated_size_cap_pct_nav"] = UNDEBATED_CAP_PCT_NAV
        size = UNDEBATED_CAP_PCT_NAV
    if size > MAX_NEW_POSITION_PCT_NAV:
        audit["caps"]["max_new_position_pct_nav"] = MAX_NEW_POSITION_PCT_NAV
        size = MAX_NEW_POSITION_PCT_NAV

    audit["size_pct_nav"] = round(size, 6)
    return round(size, 6), audit


def check_edge(expected_edge_bps: float,
               round_trip_cost_bps: float = ASSUMED_ROUND_TRIP_COST_BPS) -> None:
    """P6.3: expected edge must be ≥ edge_to_cost_multiple × estimated round-trip cost."""
    required = EDGE_TO_COST_MULTIPLE * round_trip_cost_bps
    if expected_edge_bps < required:
        raise EdgeError(
            f"expected_edge_bps={expected_edge_bps} < {EDGE_TO_COST_MULTIPLE}× round-trip cost "
            f"({required} bps) — below this you're trading for the broker's benefit (P6.3)."
        )


def check_override(*, direction: str, ballot_direction: str, rebuttal: Optional[str],
                   prior_overrides_this_month: int) -> bool:
    """P6.3 override rule. Returns True iff this proposal is a (valid) override. Fail-closed:
    an override without a written rebuttal, or past the monthly cap, raises."""
    if direction == ballot_direction:
        return False
    if not (rebuttal or "").strip():
        raise OverrideError(
            f"PM proposes {direction!r} against the ballot direction {ballot_direction!r} without "
            f"a written rebuttal addressing the majority's strongest crux — invalid (P6.3 / §5.1)."
        )
    if prior_overrides_this_month >= MAX_OVERRIDES_PER_MONTH:
        raise OverrideError(
            f"override cap reached ({prior_overrides_this_month}/{MAX_OVERRIDES_PER_MONTH} this "
            f"month) — PM defiance of the ballot is a scarce resource by construction."
        )
    return True


def check_ballot_grounding(attached: BallotSummary, tallied: BallotSummary) -> None:
    """R5 anti-canned check: the proposal's attached ballot_summary must BE the computed tally —
    a canned PM decision carrying a stale/fabricated summary fails here."""
    if attached != tallied:
        raise PMError(
            f"proposal's ballot_summary {attached!r} != the computed tally {tallied!r} — a PM "
            f"decision not grounded in the actual ballot is canned (fail-closed)."
        )


# ── LLM runner + replay reconstruction ────────────────────────────────────────────

_PM_SYS = (
    "You are PM-01, the portfolio manager. Synthesize the verified memos, the moderator's debate "
    "summary (cruxes + pre-mortem), and the ballot into ONE decision for the candidate: trade or "
    "no_trade. You are graded on what happens after you decide, including the trades you don't "
    "make. Conviction without invalidation conditions is not conviction; it's exposure. When the "
    "bear's crux is unresolved, size like it (the system will size DOWN from your conviction — you "
    "cannot set the size yourself). Proposing AGAINST the ballot direction requires a written "
    "rebuttal addressing the majority's strongest crux. Output ONLY JSON:\n"
    '{"action": "trade"|"no_trade", "direction": "long"|"short", "conviction": 0.0-1.0, '
    '"thesis": str (<=120 words), "stop_loss": str, "invalidation_conditions": [str, ...] '
    '(machine-checkable where possible), "horizon_days": int, "expected_edge_bps": int, '
    '"override_rebuttal": str|null, "what_would_reopen": str|null}'
)


@dataclass
class PMDecision:
    action: str                      # "trade" | "no_trade"
    proposal: Optional[TradeProposal]
    no_trade: Optional[dict]
    is_override: bool
    sizing_audit: Optional[dict]
    stamp: dict
    cost_usd: float


def run_pm(
    *,
    candidate: str,
    verified_memos: list[dict],
    debate_summary: DebateSummary,
    premortem_top_risks: list[str],
    ballot_summary: BallotSummary,
    ballot_direction: str,
    debate_failed: bool,
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    event_log: Optional[Any] = None,
    prior_overrides_this_month: int = 0,
) -> PMDecision:
    """One PM-01 decision: metered, replay-stamped, code-disciplined. The stored event is the
    replay source of truth (reconstruct_decision reads it back with no client)."""
    spec = manifest.resolve_runtime(PM_ROLE)
    user = (
        f"Candidate: {candidate}\n\n"
        + "\n\n".join(f"--- VERIFIED MEMO ({m.get('agent_id', '?')}) ---\n{json.dumps(m)}"
                      for m in verified_memos)
        + f"\n\n--- MODERATOR DEBATE SUMMARY ---\n{debate_summary.model_dump_json()}"
        + f"\n\n--- BALLOT (computed tally) ---\n{ballot_summary.model_dump_json()}"
        + f"\nWinning direction: {ballot_direction}"
        + "\nCurrent portfolio: empty (Phase-1 start); this would be a NEW position."
        + "\n\nDecide. JSON only."
    )
    cfg_version = load_config().config_version
    last: Exception | None = None
    raw: Optional[dict] = None
    cost = 0.0
    for _attempt in range(2):  # one retry (P2 mirror)
        resp = client.call(model_version=spec.model_version, provider=spec.provider,
                           messages=[{"role": "system", "content": _PM_SYS},
                                     {"role": "user", "content": user}],
                           response_format={"type": "json_object"}, max_tokens=4096)
        cost += resp.usage.cost_usd
        try:
            if resp.finish_reason == "length":
                raise ValueError("PM-01 reply truncated")
            s = resp.text.find("{")
            if s == -1:
                raise ValueError("no JSON in PM-01 reply")
            raw, _ = json.JSONDecoder().raw_decode(resp.text[s:])
            break
        except ValueError as e:
            last = e
            raw = None
    if raw is None:
        raise PMError(f"PM-01 failed to produce parseable JSON after retry: {last}")

    rt = ReplayTuple(trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=decision_ts,
                     agent_id=PM_ROLE, prompt_version="cp3-pm-v1", model_version=resp.model_version,
                     manifest_version=manifest.manifest_version, config_version=cfg_version,
                     code_version=code_version)
    stamp = {**rt.to_dict(), "usage": {"prompt_tokens": resp.usage.prompt_tokens,
             "completion_tokens": resp.usage.completion_tokens, "cost_usd": cost}}

    if raw.get("action") == "no_trade":
        no_trade = {"ticker": candidate, "reason": raw.get("thesis", ""),
                    "what_would_reopen": raw.get("what_would_reopen", "")}
        if event_log is not None:
            event_log.append(event_type="no_trade", cycle_id=cycle_id, agent_id=PM_ROLE,
                             payload={"no_trade": no_trade, "replay_tuple": rt.to_dict()})
        return PMDecision("no_trade", None, no_trade, False, None, stamp, round(cost, 6))

    # ── code-owned discipline (judgment came from the model; arithmetic/guards are ours) ──
    direction = raw.get("direction")
    if direction not in ("long", "short"):
        raise PMError(f"PM-01 direction {direction!r} invalid")
    is_override = check_override(direction=direction, ballot_direction=ballot_direction,
                                 rebuttal=raw.get("override_rebuttal"),
                                 prior_overrides_this_month=prior_overrides_this_month)
    check_edge(float(raw.get("expected_edge_bps", 0)))
    unresolved_crux = bool(debate_summary.unresolved_cruxes)
    size, audit = size_position(conviction=float(raw.get("conviction", 0.0)),
                                contested=ballot_summary.contested, debate_failed=debate_failed,
                                unresolved_bear_crux=unresolved_crux)

    try:
        proposal = TradeProposal(
            agent_id=PM_ROLE, ticker=candidate, direction=direction,
            size_pct_nav=size,                                  # SERVER-AUTHORITATIVE
            entry_plan=EntryPlan(type="market_open", params={}),  # Phase-1 simple rule (§7: EXEC-01 is Phase 2)
            stop_loss=str(raw.get("stop_loss", "")),
            invalidation_conditions=list(raw.get("invalidation_conditions", [])),
            horizon_days=int(raw.get("horizon_days", 0)),
            thesis=str(raw.get("thesis", "")),
            premortem_top_risks=list(premortem_top_risks),
            expected_edge_bps=int(raw.get("expected_edge_bps", 0)),
            ballot_summary=ballot_summary,                       # the COMPUTED tally, attached by code
        )
    except ValidationError as e:
        raise PMError(f"PM-01 output failed the §2.3 TradeProposal schema: {e}") from e
    check_ballot_grounding(proposal.ballot_summary, ballot_summary)

    if event_log is not None:
        event_log.append(event_type="proposal_written", cycle_id=cycle_id, agent_id=PM_ROLE,
                         payload={"proposal": proposal.model_dump(), "sizing_audit": audit,
                                  "is_override": is_override, "replay_tuple": rt.to_dict()})
        if is_override:
            event_log.append(event_type="pm_override", cycle_id=cycle_id, agent_id=PM_ROLE,
                             payload={"direction": direction, "ballot_direction": ballot_direction,
                                      "rebuttal": raw.get("override_rebuttal"),
                                      "replay_tuple": rt.to_dict()})
    logger.info("pm_decision", candidate=candidate, direction=direction, size_pct_nav=size,
                contested=ballot_summary.contested, override=is_override, cost_usd=round(cost, 6))
    return PMDecision("trade", proposal, None, is_override, audit, stamp, round(cost, 6))


def reconstruct_decision(event_log: Any, cycle_id: str) -> Optional[dict]:
    """R5 replay: read the STORED PM decision back from the event log. Takes only the log — no
    client, no manifest, no model. Replay reads the stored decision; it never re-calls the LLM."""
    events = event_log.get_events(cycle_id=cycle_id, agent_id=PM_ROLE)
    for e in reversed(events):
        if e.event_type in ("proposal_written", "no_trade"):
            return {"event_type": e.event_type, **e.payload}
    return None
