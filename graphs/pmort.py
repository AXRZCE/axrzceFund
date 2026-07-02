"""PMORT-01 — post-mortem / attribution agent (WP5 R1/R6b/R6c; agent-specifications §6.3, P9).

Family discipline (R1): PMORT-01 is T3 judge-family, resolved AT CALL TIME against the DECIDED
family (PM-01 = google ⇒ the resolver lands on a disjoint family) — REUSING the CP0 primitive
(`core.heterogeneity.resolve_judge_family`) and the existing per-family T3 manifest seats
(`VERIF-01-JUDGE-<FAMILY>`, runtime-scoped). The call site re-asserts disjointness (gut it → a
forced same-family judge passes silently → red). The ReplayTuple records agent_id=PMORT-01 with
the seat's model_version.

Grounding (R1): every citation in `knowable_at_decision_ts.citations` must reference material that
actually exists in the stored decision record — a canned post-mortem citing nothing fails
(`PMORTError`), the WP3-judge grounding pattern.

Fail-closed queueing (R6c): an LLMError after the client's bounded retries emits `pmort_pending`
(via core.episodic) — QUEUED, never skipped, never fabricated. `drain_pending` retries the queue.

§6.3 anchor carried into the prompt: "A profitable trade with a refuted thesis is a loss that
paid. Say so." Process and outcome are graded SEPARATELY (schema-enforced, core/episodic.PostMortem).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from pydantic import ValidationError

from core.episodic import (
    Episode,
    Outcome,
    PostMortem,
    capture_pmort_pending,
    capture_post_mortem,
    pending_post_mortems,
)
from core.heterogeneity import assert_judge_disjoint, resolve_judge_family
from core.llm import LLMError
from graphs.judge import JUDGE_ROLE_BY_FAMILY

logger = structlog.get_logger()


class PMORTError(Exception):
    """PMORT-01 produced an invalid/ungrounded post-mortem (fail-closed)."""


def resolve_pmort_seat(decided_family: str, manifest: Any,
                       *, override: Optional[str] = None) -> Any:
    """Call-time family resolution (REUSED primitive) + call-site disjointness assertion.
    `override` exists so a forced mis-configuration still hits the assertion (the R1 red test)."""
    available = {s.family for s in manifest.specs.values()}
    family = override if override is not None else resolve_judge_family(decided_family, available)
    # CALL-SITE enforcement (R1): gut this loop → a forced same-family PMORT passes silently → red.
    for jf in (decided_family,):
        assert_judge_disjoint(family, jf, available)
    role = JUDGE_ROLE_BY_FAMILY.get(family)
    if role is None:
        raise PMORTError(f"no T3 seat for family {family!r} (have {sorted(JUDGE_ROLE_BY_FAMILY)})")
    return manifest.resolve_runtime(role)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def check_pmort_grounding(pm: PostMortem, decision_record: dict) -> None:
    """R1 anti-canned: each knowable_at_decision_ts citation must appear in the decision record
    (normalized fragment match — first 6 tokens contiguous, or ≥0.5 token overlap with a record
    string). A verdict citing nothing that exists in the record is canned."""
    corpus = _norm(json.dumps(decision_record))
    for cited in pm.knowable_at_decision_ts.citations:
        toks = _norm(cited).split()
        windows = [" ".join(toks[i:i + 6]) for i in range(max(1, len(toks) - 5))]
        hit = any(len(w.split()) >= min(6, len(toks)) and w in corpus for w in windows)
        if not hit:
            overlap = len(set(toks) & set(corpus.split())) / max(1, len(set(toks)))
            hit = overlap >= 0.5
        if not hit:
            raise PMORTError(
                f"citation not found in the decision record: {cited[:80]!r} — a post-mortem that "
                f"cites nothing from the record is canned (fail-closed).")


_PMORT_SYS = (
    "You are PMORT-01, the post-mortem and attribution agent. Within the decision record and the "
    "outcome marks you are given: was the thesis right, wrong, or right-for-the-wrong-reasons? "
    "Skill or luck? Grade the PROCESS and the OUTCOME separately — a profitable trade with a "
    "refuted thesis is a loss that paid; say so. Answer 'was this knowable at decision_ts?' citing "
    "ONLY material present in the decision record (quote fragments verbatim). Name the single "
    "observable that, seen at decision time, would have changed the decision. If the outcome "
    "window is partial (interim), do NOT offer a generalizable lesson. Output ONLY JSON:\n"
    '{"outcome_vs_thesis": "confirmed"|"refuted"|"unrelated_path", "luck_skill_assessment": str, '
    '"premortem_hit": bool, "process_grade": 0-4, "outcome_grade": 0-4, '
    '"knowable_at_decision_ts": {"answer": bool, "citations": [verbatim fragments]}, '
    '"observable_that_would_have_changed": str, '
    '"lesson": {"text": str (<=50 words), "generalizable": bool, "tags": [str]} | null, '
    '"agent_grades": {agent_id: note}}'
)


@dataclass
class PMORTResult:
    status: str                      # "captured" | "pending"
    post_mortem: Optional[PostMortem]
    stamp: Optional[dict]
    cost_usd: float


def run_pmort(
    *,
    trade_id: str,
    ticker: str,
    sector: str,
    direction: str,
    decision_record: dict,
    outcome: Outcome,
    premortem_top_risks: list[str],
    decision_record_ref: str,
    interim: bool,
    window_days: Optional[int],
    decided_family: str,
    client: Any,
    manifest: Any,
    cycle_id: str,
    decision_ts: str,
    code_version: str,
    event_log: Any,
    tags: Optional[list[str]] = None,
) -> PMORTResult:
    """One post-mortem: disjoint seat → grounded verdict → captured (R3). On LLMError: QUEUED (R6c)."""
    spec = resolve_pmort_seat(decided_family, manifest)
    user = (
        f"--- DECISION RECORD ({decision_record_ref}) ---\n{json.dumps(decision_record)}\n\n"
        f"--- PRE-MORTEM RISKS NAMED AT DECISION TIME ---\n{json.dumps(premortem_top_risks)}\n\n"
        f"--- OUTCOME ({'INTERIM, window ' + str(window_days) + ' sessions' if interim else 'closed'}) ---\n"
        f"{outcome.model_dump_json()}\n\nWrite the post-mortem JSON."
    )
    cost = 0.0
    try:
        last: Exception | None = None
        pm: Optional[PostMortem] = None
        model_ran = ""
        for _attempt in range(2):
            # P2 pattern: ONE retry WITH ERROR FEEDBACK — schema/grounding failures are inside
            # the loop (the first WP5 smoke failed closed because only parse errors retried).
            ask = user if last is None else (
                f"{user}\n\nYOUR PREVIOUS REPLY WAS INVALID: {str(last)[:400]}\n"
                f"Reply again as ONE flat JSON object with ALL required fields at the top level.")
            resp = client.call(model_version=spec.model_version, provider=spec.provider,
                               messages=[{"role": "system", "content": _PMORT_SYS},
                                         {"role": "user", "content": ask}],
                               response_format={"type": "json_object"}, max_tokens=4096)
            cost += resp.usage.cost_usd
            model_ran = resp.model_version
            try:
                if resp.finish_reason == "length":
                    raise ValueError("PMORT reply truncated")
                s = resp.text.find("{")
                raw, _ = json.JSONDecoder().raw_decode(resp.text[s:])
                if not isinstance(raw, dict):
                    raise ValueError("top-level JSON is not an object")
                # unwrap a single-key envelope like {"post_mortem": {...}} (observed model habit)
                if len(raw) == 1 and isinstance(next(iter(raw.values())), dict):
                    raw = next(iter(raw.values()))
                raw.update(trade_id=trade_id, ticker=ticker, interim=interim,
                           window_days=window_days)
                pm = PostMortem.model_validate(raw)
                check_pmort_grounding(pm, decision_record)
                break
            except (ValueError, ValidationError, PMORTError) as e:
                last = e
                pm = None
        if pm is None:
            raise PMORTError(f"PMORT-01 failed to produce a valid, grounded post-mortem "
                             f"after retry: {last}")

        episode = Episode(trade_id=trade_id, cycle_id=cycle_id, ticker=ticker, sector=sector,
                          direction=direction, tags=tags or [],
                          decision_record_ref=decision_record_ref, outcome=outcome,
                          premortem_hit=pm.premortem_hit, post_mortem_ref=f"event:post_mortem:{trade_id}",
                          lesson_candidate=pm.lesson, interim=interim, window_days=window_days)
        stamp = capture_post_mortem(event_log=event_log, post_mortem=pm, episode=episode,
                                    manifest=manifest, cycle_id=cycle_id, decision_ts=decision_ts,
                                    code_version=code_version,
                                    agent_model_version=model_ran)
        logger.info("pmort_complete", trade_id=trade_id, verdict=pm.outcome_vs_thesis,
                    process=pm.process_grade, outcome_grade=pm.outcome_grade,
                    interim=interim, cost_usd=round(cost, 6))
        return PMORTResult("captured", pm, stamp, round(cost, 6))
    except LLMError as e:  # R6c: queued, never skipped, never fabricated
        capture_pmort_pending(event_log=event_log, trade_id=trade_id, cycle_id=cycle_id,
                              reason=str(e)[:300])
        return PMORTResult("pending", None, None, round(cost, 6))


def drain_pending(*, event_log: Any, retry_fn: Any) -> list[str]:
    """R6c drain: retry each queued post-mortem via `retry_fn(pending_payload) -> PMORTResult`.
    Returns the trade_ids that captured this pass; still-failing items remain queued (the queue is
    derived from the log, so it survives restarts by construction)."""
    drained = []
    for p in pending_post_mortems(event_log):
        result = retry_fn(p)
        if result.status == "captured":
            drained.append(p["trade_id"])
    return drained
