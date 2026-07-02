"""VERIF-01 as T3 LLM debate judge (WP3 CP4, ruling R6) — §6.5's deferred LLM duties.

The WP2 deterministic validator (graphs/verif01.py) is RETAINED UNCHANGED as the schema/citation
gate; this module adds the T3 judging layer: scoring both debate sides on evidence quality, attack
relevance, and concession honesty (agent-specifications §6.5 / P4.4), with the LLM-judge bias
controls the spec names — transcript sides MASKED (A/B), order randomized on a deterministic seed.

Family disjointness is resolved AT CALL TIME, never hardcoded (configuration.md §3 T3_judge:
"strongest available family ≠ judged agents per call"):

    judge_family_for(judged_families, available)  →  a family disjoint from EVERY judged family,
    enforced at THIS call site via core.heterogeneity.assert_judge_disjoint (fail-closed; the
    genuinely-no-alternative case is LOGGED, never silent). The chosen family seats that family's
    manifest judge role (VERIF-01-JUDGE-<FAMILY>, runtime-scoped).

Anti-canned grounding: the judge must cite WHICH claims it scored (`claims_scored`), and every
cited claim must actually appear in the transcript — `check_judge_grounding` fails a verdict that
ignores the transcript. Scores attach to the debate record and decide NOTHING by themselves (P4.4).
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import structlog
from pydantic import BaseModel, Field, ValidationError

from core.config import load_config
from core.heterogeneity import assert_judge_disjoint
from core.llm import OpenRouterClient
from core.manifest import Manifest
from core.replay import ReplayTuple, new_trade_id
from graphs.state import DebateTurn

logger = structlog.get_logger()

JUDGE_ROLE_BY_FAMILY = {
    "google": "VERIF-01-JUDGE-GOOGLE",
    "openai": "VERIF-01-JUDGE-OPENAI",
    "chinese": "VERIF-01-JUDGE-CHINESE",
}


class JudgeError(Exception):
    """The judge could not produce a valid, transcript-grounded verdict (fail-closed)."""


class SideScores(BaseModel):
    model_config = {"extra": "forbid"}
    evidence: int = Field(ge=0, le=4)
    attack_relevance: int = Field(ge=0, le=4)
    concession_honesty: int = Field(ge=0, le=4)
    claims_scored: list[str] = Field(min_length=1)  # WHICH transcript claims were judged (anti-canned)


class DebateScores(BaseModel):
    model_config = {"extra": "forbid"}
    bull: SideScores
    bear: SideScores


def judge_family_for(
    judged_families: Iterable[str],
    available_families: Iterable[str],
    *,
    override: Optional[str] = None,
) -> str:
    """Resolve the judge FAMILY at call time: a family disjoint from EVERY judged family.

    `override` exists so a mis-configuration (someone forcing a family) still hits the CALL-SITE
    disjointness assertion below — the guard is here, not only in the library. Deterministic
    (sorted) so replay is stable. No-alternative ⇒ the assertion's logged fallback applies.
    """
    judged = set(judged_families)
    available = set(available_families)
    if override is not None:
        family = override
    else:
        disjoint = sorted(available - judged)
        family = disjoint[0] if disjoint else sorted(judged)[0]  # no-alternative fallback (logged below)
    # CALL-SITE enforcement (R6): gut this loop → a forced same-family judge passes silently → red.
    for jf in judged:
        assert_judge_disjoint(family, jf, available)
    return family


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def _token_jaccard(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def check_judge_grounding(scores: DebateScores, turns: list[DebateTurn]) -> None:
    """Anti-canned check: every claim the judge says it scored must actually appear in the
    transcript. The corpus is EVERYTHING the judge was shown per turn — argument points, attacks,
    concessions, steelman (the CP4 smoke caught the original points-only corpus rejecting a judge
    that legitimately quoted a concession). Grounded iff a contiguous 6-token window of the cited
    text appears in the corpus, OR the cited text has ≥0.5 token-Jaccard with some single
    transcript segment (light-paraphrase tolerance). A verdict citing claims that exist nowhere in
    the debate is canned — fail-closed."""
    segments = [
        _norm(s) for t in turns
        for s in ([f"{a.point} {a.attacks or ''}" for a in t.arguments]
                  + list(t.concessions) + [t.steelman_of_opponent])
        if s and _norm(s)
    ]
    corpus = " ".join(segments)
    for side_name, side in (("bull", scores.bull), ("bear", scores.bear)):
        for cited in side.claims_scored:
            frag_tokens = _norm(cited).split()
            windows = [" ".join(frag_tokens[i:i + 6])
                       for i in range(max(1, len(frag_tokens) - 5))]
            window_hit = any(len(w.split()) >= min(6, len(frag_tokens)) and w in corpus
                             for w in windows)
            jaccard_hit = any(_token_jaccard(_norm(cited), seg) >= 0.5 for seg in segments)
            if not (window_hit or jaccard_hit):
                raise JudgeError(
                    f"judge verdict cites a claim not present in the transcript "
                    f"({side_name}: {cited[:80]!r}) — a verdict that ignores the transcript is "
                    f"canned (fail-closed)."
                )


_JUDGE_SYS = (
    "You are VERIF-01 acting as the debate judge. You see an ANONYMIZED debate transcript between "
    "SIDE A and SIDE B (you are not told which is bull or bear) plus the verified memos they argued "
    "from. Score EACH side 0-4 on: evidence (cite-density and use of the memo's actual figures), "
    "attack_relevance (did attacks engage the opponent's real claims), concession_honesty (did the "
    "side acknowledge the opponent's best points). Do NOT reward eloquence or length. In "
    "claims_scored, QUOTE the exact claim texts you evaluated (at least one per side, verbatim "
    "fragments from the transcript). Output ONLY JSON: "
    '{"A": {"evidence": int, "attack_relevance": int, "concession_honesty": int, '
    '"claims_scored": [str]}, "B": {...}}'
)


@dataclass
class JudgeResult:
    judge_family: str
    judge_role: str
    scores: DebateScores
    stamp: dict
    cost_usd: float


def run_judge_debate(
    *,
    turns: list[DebateTurn],
    verified_memos: list[dict],
    judged_families: Iterable[str],
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    seed_key: str,
) -> JudgeResult:
    """Score one debate with a call-time-resolved, family-disjoint judge. Sides masked (A/B),
    order randomized on a deterministic seed; scores mapped back to bull/bear afterwards."""
    available = {s.family for s in manifest.specs.values()}
    family = judge_family_for(judged_families, available)
    role = JUDGE_ROLE_BY_FAMILY.get(family)
    if role is None:
        raise JudgeError(f"no manifest judge seat for family {family!r} (have {sorted(JUDGE_ROLE_BY_FAMILY)})")
    spec = manifest.resolve_runtime(role)

    # mask + deterministic order randomization (P4.4 / §6.5 bias controls)
    rng = random.Random(int.from_bytes(seed_key.encode(), "big") % (2**31))
    sides = ["bull", "bear"]
    rng.shuffle(sides)
    label_of = {sides[0]: "A", sides[1]: "B"}
    masked = "\n\n".join(
        f"--- SIDE {label_of[t.position]} / ROUND {t.round} ---\n"
        + json.dumps({"arguments": [a.model_dump() for a in t.arguments],
                      "concessions": t.concessions, "steelman": t.steelman_of_opponent})
        for t in turns
    )
    memo_block = "\n\n".join(json.dumps(m) for m in verified_memos)
    user = (f"--- VERIFIED MEMOS ---\n{memo_block}\n\n--- MASKED TRANSCRIPT ---\n{masked}\n\n"
            f"Score side A and side B. JSON only.")

    cfg = load_config().config_version
    last: Exception | None = None
    cost = 0.0
    for _attempt in range(2):
        resp = client.call(model_version=spec.model_version, provider=spec.provider,
                           messages=[{"role": "system", "content": _JUDGE_SYS},
                                     {"role": "user", "content": user}],
                           response_format={"type": "json_object"}, max_tokens=4096)
        cost += resp.usage.cost_usd
        try:
            if resp.finish_reason == "length":
                raise ValueError("judge reply truncated")
            s = resp.text.find("{")
            raw, _ = json.JSONDecoder().raw_decode(resp.text[s:])
            unmasked = {side: raw[label_of[side]] for side in ("bull", "bear")}
            scores = DebateScores.model_validate(unmasked)
            check_judge_grounding(scores, turns)
            rt = ReplayTuple(trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=decision_ts,
                             agent_id=role, prompt_version="cp4-judge-v1",
                             model_version=resp.model_version,
                             manifest_version=manifest.manifest_version, config_version=cfg,
                             code_version=code_version)
            stamp = {**rt.to_dict(), "usage": {"prompt_tokens": resp.usage.prompt_tokens,
                     "completion_tokens": resp.usage.completion_tokens, "cost_usd": cost}}
            logger.info("debate_judged", judge_family=family, judge_role=role,
                        bull_evidence=scores.bull.evidence, bear_evidence=scores.bear.evidence,
                        cost_usd=round(cost, 6))
            return JudgeResult(family, role, scores, stamp, round(cost, 6))
        except (ValueError, KeyError, ValidationError, JudgeError) as e:
            last = e
    raise JudgeError(f"judge failed to produce a grounded verdict after retry: {last}")
