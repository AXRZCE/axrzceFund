"""Shadow-ensemble (WP3 CP4, ruling R7) — decorrelation MEASURED, not assumed.

Alternate-family models run IN SHADOW on real decisions: each shadow casts the would-be
stance/conviction it would have voted, which is LOGGED (event log `shadow_vote` events + the
results artifact) and fed to a decorrelation metric. Shadow outputs NEVER touch the live decision.

**Isolation is structural, not promised:** this module deliberately imports NEITHER `CycleState`
nor `TradeProposal` and returns only frozen `ShadowVote` records — there is no code path by which
a shadow output can write a live decision field. A committed source-scan test
(tests/test_shadow.py) fails if anyone adds such an import; the deep loop never imports this
module either (the smoke/orchestration calls it out-of-band, after the live decision is made).

Shadow seats resolve via `Manifest.resolve()` — they are the CP1 validation-scoped models
(DeepSeek + the Western baseline), reused as shadow families. Runtime seating stays fail-closed
(`resolve_runtime` still rejects them); shadowing is an evidence activity, like the CP1 comparison.

Decorrelation metric (Phase-1 minimum): pairwise stance-agreement rate across families. N is small
this WP — the metric matures over WP6's daily cycles (see the shadow-budget note in the readout).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import structlog

from core.config import load_config
from core.llm import OpenRouterClient
from core.manifest import Manifest
from core.replay import ReplayTuple, new_trade_id

logger = structlog.get_logger()

# CP1 validation-scoped models, reused as shadow families (scope stays validation — runtime
# seating remains fail-closed; shadows are evidence, not decisions).
DEFAULT_SHADOW_ROLES = ["BULL-01-CAND-DEEPSEEK", "BULL-01-BASELINE-WEST"]

_SHADOW_SYS = (
    "You are a SHADOW analyst: your vote is recorded for decorrelation measurement only and "
    "affects nothing. Given the verified memos and the moderator's debate summary, state the "
    "stance you would take. Output ONLY JSON: "
    '{"stance": "long"|"short"|"no_position", "conviction": 0.0-1.0}'
)


class ShadowError(Exception):
    """Shadow measurement failed (fail-closed for the MEASUREMENT — never affects the decision)."""


@dataclass(frozen=True)
class ShadowVote:
    role: str
    family: str
    model_version: str
    stance: str
    conviction: float
    stamp: dict


def run_shadow_votes(
    *,
    verified_memos: list[dict],
    debate_summary_json: str,
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    event_log: Optional[Any] = None,
    shadow_roles: Optional[list[str]] = None,
) -> tuple[list[ShadowVote], float]:
    """Cast the shadow votes. Returns (votes, cost). Writes ONLY shadow_vote events — no state."""
    cfg = load_config().config_version
    votes: list[ShadowVote] = []
    cost = 0.0
    context = (
        "\n\n".join(json.dumps(m) for m in verified_memos)
        + f"\n\n--- MODERATOR DEBATE SUMMARY ---\n{debate_summary_json}\n\nYour shadow vote. JSON only."
    )
    for role in shadow_roles or DEFAULT_SHADOW_ROLES:
        spec = manifest.resolve(role)  # validation scope allowed HERE (evidence path, not a seat)
        resp = client.call(model_version=spec.model_version, provider=spec.provider,
                           messages=[{"role": "system", "content": _SHADOW_SYS},
                                     {"role": "user", "content": context}],
                           response_format={"type": "json_object"}, max_tokens=2048)
        cost += resp.usage.cost_usd
        s = resp.text.find("{")
        raw, _ = json.JSONDecoder().raw_decode(resp.text[s:])
        stance = raw.get("stance")
        if stance not in ("long", "short", "no_position"):
            raise ShadowError(f"shadow {role} returned invalid stance {stance!r}")
        rt = ReplayTuple(trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=decision_ts,
                         agent_id=f"SHADOW:{role}", prompt_version="cp4-shadow-v1",
                         model_version=resp.model_version,
                         manifest_version=manifest.manifest_version, config_version=cfg,
                         code_version=code_version)
        stamp = {**rt.to_dict(), "usage": {"prompt_tokens": resp.usage.prompt_tokens,
                 "completion_tokens": resp.usage.completion_tokens,
                 "cost_usd": resp.usage.cost_usd}}
        vote = ShadowVote(role=role, family=spec.family, model_version=spec.model_version,
                          stance=stance, conviction=float(raw.get("conviction", 0.0)), stamp=stamp)
        votes.append(vote)
        if event_log is not None:  # the LOG is the measurement — remove it and R7 has nothing
            event_log.append(event_type="shadow_vote", cycle_id=cycle_id, agent_id=vote.stamp["agent_id"],
                             payload={"role": role, "family": spec.family, "stance": stance,
                                      "conviction": vote.conviction, "replay_tuple": rt.to_dict()})
        logger.info("shadow_vote", role=role, family=spec.family, stance=stance,
                    conviction=vote.conviction)
    return votes, round(cost, 6)


def compute_decorrelation(
    live_stances: dict[str, str],
    shadow_votes: list[ShadowVote],
) -> dict[str, Any]:
    """Pairwise stance-agreement across families, from the LOGGED votes (measured, not assumed).

    `live_stances` maps live voter family-tagged ids (e.g. "BULL-01(chinese)") to stances;
    shadows contribute their own. Returns per-pair agreement + the mean agreement rate.
    Fail-closed on nothing to measure — an empty shadow log means R7 did not happen.
    """
    if not shadow_votes:
        raise ValueError("no shadow votes logged — decorrelation cannot be measured (R7 red)")
    all_stances: dict[str, str] = dict(live_stances)
    for v in shadow_votes:
        all_stances[f"SHADOW:{v.role}({v.family})"] = v.stance
    ids = sorted(all_stances)
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pairs.append({"a": a, "b": b, "agree": all_stances[a] == all_stances[b]})
    agree_rate = sum(p["agree"] for p in pairs) / len(pairs)
    return {"n_voters": len(ids), "n_pairs": len(pairs), "pairs": pairs,
            "stance_agreement_rate": round(agree_rate, 4),
            "note": "N=1 cycle at WP3 — the metric matures over WP6's daily cycles"}
