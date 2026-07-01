"""FUND-TECH — Sector Fundamental Analyst (agent-specifications §3.2), WP2 real agent.

Reads point-in-time fundamentals for a candidate from a committed, R1-gated fixture (no live
store, no look-ahead), and produces a §2.1 ResearchMemo + §3.2 `valuation_block` via a metered
OpenRouter call (the manifest's FUND-TECH model + provider pin). The memo is:
  - schema-valid + VERIF-01-validated (R3),
  - metered with the real per-call USD cost (R4),
  - replay-stamped (R5: model_version + manifest_version + provider + decision_ts),
  - grounded in THAT fixture's data — a canned memo that ignores the fixture fails the grounding
    check (its ticker/numbers won't match).

The agent reads ONLY the fixture (which was sourced through pit_store at as_known_at=decision_ts),
so R2 holds by construction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from core.event_log import EventLog
from core.config import load_config
from core.llm import LLMResponse, OpenRouterClient
from core.manifest import Manifest
from core.replay import ReplayTuple, new_trade_id
from data.fixtures.harness import Fixture
from graphs.verif01 import VerificationResult, verify_memo

ROLE = "FUND-TECH"
PROMPT_VERSION = "fund-tech-v1"

SYSTEM = """You are FUND-TECH, a point-in-time sector fundamental analyst. Your mission: produce a \
falsifiable fundamental view of the candidate — valuation, earnings quality, balance-sheet risk — \
using ONLY the point-in-time data provided. You see nothing dated after the decision timestamp.

Standing orders:
- Numbers you cannot cite do not exist. Every claim of claim_type "fact" MUST cite at least one \
doc_id from the DATA block in its `evidence`. Inferences/estimates may reason beyond the data but \
must be labelled as such.
- Your fair-value range will be graded against reality. State the assumption that, if wrong, breaks \
your thesis.
- A short, falsifiable thesis beats a long narrative.

Output ONLY a single JSON object (no markdown, no prose outside it) with EXACTLY these fields:
{
  "ticker": "<the candidate ticker>",
  "stance": "long" | "short" | "neutral" | "avoid",
  "conviction": <number 0.0-1.0>,
  "horizon_days": <integer>,
  "thesis": "<= 150 words, falsifiable",
  "key_claims": [   // between 3 and 7 items
    {"claim": "<text>", "evidence": ["<doc_id>", ...], "claim_type": "fact" | "inference" | "estimate"}
  ],
  "catalysts": [{"event": "<text>", "expected_window": "<date range>"}],
  "invalidation_conditions": ["<observable, checkable condition>"],
  "risks": ["<text>"],
  "what_would_change_my_mind": "<text, required>",
  "valuation_block": {
    "method": "dcf" | "multiples" | "sotp",
    "fair_value_range": [<low number>, <high number>],
    "key_assumptions": ["<text>", ...]
  }
}"""


def _candidate_doc_block(fixture: Fixture, candidate: str) -> tuple[str, list[str]]:
    """Render the candidate's fixture data as a doc-id'd block the model can cite. Returns
    (text, doc_ids)."""
    doc_ids: list[str] = []
    lines: list[str] = [f"DATA for {candidate}, knowable as of {fixture.decision_ts} (point-in-time):", ""]

    lines.append("Fundamentals (Sharadar SF1; latest 4 periods per indicator):")
    funds = fixture.payload.get("fundamentals", {})
    for indicator, rows in funds.items():
        crows = sorted(
            [r for r in rows if r.get("ticker") == candidate],
            key=lambda r: r.get("available_at", ""), reverse=True,
        )[:4]
        for r in crows:
            doc_id = f"sf1:{candidate}:{indicator}:{r.get('period')}"
            doc_ids.append(doc_id)
            lines.append(f"  [{doc_id}] {indicator}={r.get('value')} (period {r.get('period')})")
    lines.append("")

    bars = sorted(
        [b for b in fixture.payload.get("price_bars", []) if b.get("ticker") == candidate],
        key=lambda b: b.get("as_of", ""),
    )
    if bars:
        last = bars[-1]
        doc_id = f"sep:{candidate}:{str(last.get('as_of'))[:10]}"
        doc_ids.append(doc_id)
        closes = [b.get("close") for b in bars if b.get("close") is not None]
        lines.append(
            f"Price context: {len(bars)} daily bars; latest close [{doc_id}] {last.get('close')} "
            f"(window low {min(closes) if closes else 'n/a'}, high {max(closes) if closes else 'n/a'})."
        )
    return "\n".join(lines), doc_ids


@dataclass
class AgentRun:
    candidate: str
    memo: dict
    verification: VerificationResult
    usage_cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    replay: ReplayTuple
    response: LLMResponse


def run_fund_tech(
    *,
    fixture: Fixture,
    candidate: str,
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    code_version: str,
    event_log: Optional[EventLog] = None,
    max_tokens: int = 8000,
) -> AgentRun:
    """Run FUND-TECH on one fixture candidate. Returns the validated, metered, replay-stamped run."""
    spec = manifest.resolve_runtime(ROLE)  # runtime path — a validation-scoped role fail-closes (CP2 S1)
    data_block, _doc_ids = _candidate_doc_block(fixture, candidate)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Candidate ticker: {candidate}\n\n{data_block}\n\n"
                                     f"Produce the FUND-TECH memo JSON for {candidate}."},
    ]

    resp = client.call(
        model_version=spec.model_version, messages=messages, provider=spec.provider,
        response_format={"type": "json_object"}, max_tokens=max_tokens,
        event_log=event_log, cycle_id=cycle_id,
    )
    if resp.finish_reason == "length":
        raise ValueError(
            f"FUND-TECH output truncated at max_tokens={max_tokens} "
            f"(completion_tokens={resp.usage.completion_tokens}) — increase max_tokens"
        )

    # Robustly extract the first JSON object: models may wrap it in a code fence or append
    # trailing prose/reasoning. Find the first '{' and decode one complete object, ignore the rest.
    text = resp.text.strip()
    start = text.find("{")
    if start == -1:
        raise ValueError(f"FUND-TECH returned no JSON object: {text[:200]!r}")
    memo, _end = json.JSONDecoder().raw_decode(text[start:])
    memo.setdefault("agent_id", ROLE)
    memo.setdefault("ticker", candidate)

    verification = verify_memo(memo, agent_role=ROLE)

    replay = ReplayTuple(
        trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=fixture.decision_ts,
        agent_id=ROLE, prompt_version=PROMPT_VERSION, model_version=resp.model_version,
        manifest_version=manifest.manifest_version,        # WP3 R5: manifest hash in its own field
        config_version=load_config().config_version,       # configuration.md hash (no longer conflated)
        code_version=code_version,
    )

    if event_log is not None:
        event_log.append(
            event_type="memo_written", cycle_id=cycle_id, decision_ts=fixture.decision_ts,
            trade_id=replay.trade_id, agent_id=ROLE,
            payload={
                "memo": memo,
                "replay_tuple": replay.to_dict(),
                "provider": spec.provider,
                "usage": {"prompt_tokens": resp.usage.prompt_tokens,
                          "completion_tokens": resp.usage.completion_tokens,
                          "cost_usd": resp.usage.cost_usd},
                "verification": {"valid": verification.valid,
                                 "schema_violations": verification.schema_violations,
                                 "stripped_claims": verification.stripped_claims},
                "fixture": {"fixture_id": fixture.fixture_id, "content_hash": fixture.content_hash},
            },
        )

    return AgentRun(
        candidate=candidate, memo=memo, verification=verification,
        usage_cost_usd=resp.usage.cost_usd, prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens, replay=replay, response=resp,
    )


if __name__ == "__main__":
    import json as _json
    from pathlib import Path

    from core.manifest import load_manifest
    from data.fixtures.harness import load_fixture

    man = load_manifest()
    fx = load_fixture(Path("data/fixtures/golden/fund_tech_20260624.json"),
                      for_roles=[ROLE], manifest=man)
    run = run_fund_tech(
        fixture=fx, candidate="BNC", client=OpenRouterClient(), manifest=man,
        cycle_id="cycle_20260624_0001", code_version="dev",
    )
    print("=== FUND-TECH memo (BNC) ===")
    print(_json.dumps(run.memo, indent=2)[:2400])
    print("\nVERIF-01 valid:", run.verification.valid,
          "| violations:", run.verification.schema_violations,
          "| stripped:", len(run.verification.stripped_claims))
    print(f"tokens: prompt={run.prompt_tokens} completion={run.completion_tokens} "
          f"| cost_usd=${run.usage_cost_usd:.6f} | model={run.response.model_version}")
    print("replay:", run.replay.to_dict())
