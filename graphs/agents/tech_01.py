"""TECH-01 — Technical / Price-Action Analyst (agent-specifications §3.4), WP2 real agent.

Reads point-in-time OHLCV for a candidate from a committed, R1-gated fixture (no live store, no
look-ahead) and produces a §2.1 ResearchMemo + §3.4 `technical_block` via a metered OpenRouter
call (the manifest's TECH-01 model + provider pin). Like FUND-TECH, the memo is:
  - schema-valid + VERIF-01-validated (R3),
  - metered with the real per-call USD cost (R4),
  - replay-stamped (R5: model_version + manifest_version + provider + decision_ts),
  - grounded in THAT fixture's data — every fact cites a `sep:` price doc_id from the DATA block,
    so a canned memo that ignores the fixture fails the grounding check.

§3.4 discipline: plain description over prediction. The four `technical_block` fields (trend,
support/resistance levels, ADV liquidity context, abnormal volume) are OBJECTIVE price structure
— this module computes them deterministically from the fixture's bars and hands the model the
computed values + the citable bars; the model's judgment is the thesis/stance/claims, not the
arithmetic. TECH-01 makes NO fundamental claims and (per protocol) its stance alone can never
carry a candidate to debate.
"""

from __future__ import annotations

import json
from typing import Optional

from core.event_log import EventLog
from core.llm import OpenRouterClient
from core.manifest import Manifest
from core.replay import ReplayTuple, new_trade_id
from data.fixtures.harness import Fixture
from graphs.agents.fund_tech import AgentRun  # shared, role-generic run container
from graphs.verif01 import verify_memo

ROLE = "TECH-01"
PROMPT_VERSION = "tech-01-v1"

# Proposed position notional for the ADV liquidity context (§3.4). A fixed, disclosed convention so
# adv_pct_at_proposed_size is a checkable number rather than a guess.
PROPOSED_NOTIONAL_USD = 1_000_000.0

SYSTEM = """You are TECH-01, a point-in-time technical / price-action analyst. Your mission: \
describe the candidate's price and volume STRUCTURE — trend state, support/resistance levels, \
liquidity (ADV) context, and abnormal activity — using ONLY the point-in-time OHLCV provided. You \
see nothing dated after the decision timestamp.

Standing orders:
- Plain description over prediction. Your most valuable output is honest liquidity context and \
levels, not forecasts. Avoid pattern pareidolia — restrict yourself to plain, checkable structure.
- Numbers you cannot cite do not exist. Every claim of claim_type "fact" MUST cite at least one \
price doc_id (form sep:TICKER:YYYY-MM-DD) from the DATA block in its `evidence`.
- The DATA block gives you the pre-computed technical_block values derived from the cited bars. \
Use THOSE EXACT values in your technical_block (do not recompute or eyeball them).
- You make NO fundamental claims (earnings, valuation, balance sheet). Those are out of scope.

Output ONLY a single JSON object (no markdown, no prose outside it) with EXACTLY these fields:
{
  "ticker": "<the candidate ticker>",
  "stance": "long" | "short" | "neutral" | "avoid",
  "conviction": <number 0.0-1.0>,
  "horizon_days": <integer>,
  "thesis": "<= 150 words, falsifiable, describing the price/volume structure",
  "key_claims": [   // between 3 and 7 items
    {"claim": "<text>", "evidence": ["sep:TICKER:YYYY-MM-DD", ...], "claim_type": "fact" | "inference" | "estimate"}
  ],
  "catalysts": [{"event": "<text>", "expected_window": "<date range>"}],
  "invalidation_conditions": ["<observable, checkable condition, e.g. a level break>"],
  "risks": ["<text>"],
  "what_would_change_my_mind": "<text, required>",
  "technical_block": {
    "trend": "up" | "down" | "range",
    "key_levels": [<price level number>, ...],
    "adv_pct_at_proposed_size": <number>,
    "abnormal_volume": true | false
  }
}"""


def _ma(vals: list[float], w: int) -> float:
    """Trailing simple moving average over the last `w` values (or all, if fewer)."""
    tail = vals[-w:] if len(vals) >= w else vals
    return sum(tail) / len(tail) if tail else 0.0


def _price_doc_block(
    fixture: Fixture, candidate: str, proposed_notional_usd: float = PROPOSED_NOTIONAL_USD
) -> tuple[str, list[str], dict]:
    """Render the candidate's price bars as a doc-id'd, indicator-annotated block the model can
    cite, and compute the objective §3.4 technical_block. Returns (text, doc_ids, computed_block)."""
    # Use the SEP backtest series (deep EOD history); the same fixture may also hold sparse IEX
    # live-feed bars for a liquid name — those are a different source/granularity, out of scope here.
    bars = sorted(
        [b for b in fixture.payload.get("price_bars", [])
         if b.get("ticker") == candidate and b.get("source") == "sep"],
        key=lambda b: str(b.get("as_of")),
    )
    doc_ids: list[str] = []
    lines = [f"DATA for {candidate}, knowable as of {fixture.decision_ts} (point-in-time OHLCV):", ""]
    if not bars:
        return "\n".join(lines + ["No price bars available."]), doc_ids, {}

    def did(bar: dict) -> str:
        return f"sep:{candidate}:{str(bar.get('as_of'))[:10]}"

    closes = [float(b["close"]) for b in bars if b.get("close") is not None]
    vols = [float(b["volume"]) for b in bars if b.get("volume") is not None]
    n = len(bars)
    last = bars[-1]
    last_close = float(last["close"])
    last_vol = float(last.get("volume") or 0.0)

    ma20, ma50, ma200 = _ma(closes, 20), _ma(closes, 50), _ma(closes, 200)
    if ma50 > ma200 and last_close >= ma50:
        trend = "up"
    elif ma50 < ma200 and last_close <= ma50:
        trend = "down"
    else:
        trend = "range"

    hi_bar = max(bars, key=lambda b: float(b.get("high") or b.get("close") or 0.0))
    lo_bar = min(bars, key=lambda b: float(b.get("low") or b.get("close") or 1e18))
    recent = bars[-20:] if n >= 20 else bars
    rhi_bar = max(recent, key=lambda b: float(b.get("high") or b.get("close") or 0.0))
    rlo_bar = min(recent, key=lambda b: float(b.get("low") or b.get("close") or 1e18))
    window_high = float(hi_bar.get("high") or hi_bar.get("close"))
    window_low = float(lo_bar.get("low") or lo_bar.get("close"))
    recent_high = float(rhi_bar.get("high") or rhi_bar.get("close"))
    recent_low = float(rlo_bar.get("low") or rlo_bar.get("close"))
    key_levels = sorted({round(window_low, 4), round(recent_low, 4),
                         round(recent_high, 4), round(window_high, 4)})

    adv20 = (sum(vols[-20:]) / min(20, len(vols))) if vols else 0.0
    proposed_shares = proposed_notional_usd / last_close if last_close else 0.0
    adv_pct = round((proposed_shares / adv20 * 100.0), 4) if adv20 else 0.0
    abnormal = bool(adv20 and last_vol > 2.0 * adv20)

    # doc_ids for the bars that anchor each cited figure (all are real fixture bars).
    for b in (last, hi_bar, lo_bar, rhi_bar, rlo_bar):
        d = did(b)
        if d not in doc_ids:
            doc_ids.append(d)

    lines += [
        f"Window: {n} daily bars, {str(bars[0].get('as_of'))[:10]} .. {str(last.get('as_of'))[:10]}.",
        f"Latest close [{did(last)}] = {last_close:.4f}; latest volume = {last_vol:,.0f} shares.",
        f"Moving averages: MA20={ma20:.4f}, MA50={ma50:.4f}, MA200={ma200:.4f} "
        f"(MA50 {'>' if ma50 > ma200 else '<='} MA200; last close {'>=' if last_close >= ma50 else '<'} MA50) "
        f"-> trend '{trend}'.",
        f"Levels: window high [{did(hi_bar)}]={window_high:.4f}, window low [{did(lo_bar)}]={window_low:.4f}, "
        f"20d high [{did(rhi_bar)}]={recent_high:.4f}, 20d low [{did(rlo_bar)}]={recent_low:.4f}.",
        f"Liquidity: 20-day ADV={adv20:,.0f} shares. Proposed size ${proposed_notional_usd:,.0f} "
        f"~= {proposed_shares:,.0f} shares -> adv_pct_at_proposed_size={adv_pct}%.",
        f"Abnormal volume: latest {last_vol:,.0f} vs 2x ADV {2 * adv20:,.0f} -> {abnormal}.",
        "",
        "Pre-computed technical_block (use these EXACT values — derived from the cited bars above):",
        f"  trend={trend}; key_levels={key_levels}; "
        f"adv_pct_at_proposed_size={adv_pct}; abnormal_volume={abnormal}",
    ]
    computed = {"trend": trend, "key_levels": key_levels,
                "adv_pct_at_proposed_size": adv_pct, "abnormal_volume": abnormal}
    return "\n".join(lines), doc_ids, computed


def run_tech_01(
    *,
    fixture: Fixture,
    candidate: str,
    client: OpenRouterClient,
    manifest: Manifest,
    cycle_id: str,
    code_version: str,
    event_log: Optional[EventLog] = None,
    max_tokens: int = 3000,
) -> AgentRun:
    """Run TECH-01 on one fixture candidate. Returns the validated, metered, replay-stamped run."""
    spec = manifest.resolve(ROLE)
    data_block, _doc_ids, computed = _price_doc_block(fixture, candidate)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Candidate ticker: {candidate}\n\n{data_block}\n\n"
                                     f"Produce the TECH-01 memo JSON for {candidate}."},
    ]

    resp = client.call(
        model_version=spec.model_version, messages=messages, provider=spec.provider,
        response_format={"type": "json_object"}, max_tokens=max_tokens,
        event_log=event_log, cycle_id=cycle_id,
    )
    if resp.finish_reason == "length":
        raise ValueError(
            f"TECH-01 output truncated at max_tokens={max_tokens} "
            f"(completion_tokens={resp.usage.completion_tokens}) — increase max_tokens"
        )

    text = resp.text.strip()
    start = text.find("{")
    if start == -1:
        raise ValueError(f"TECH-01 returned no JSON object: {text[:200]!r}")
    memo, _end = json.JSONDecoder().raw_decode(text[start:])
    memo.setdefault("agent_id", ROLE)
    memo.setdefault("ticker", candidate)
    # The technical_block is OBJECTIVE arithmetic (§3.4), not model judgment: make it AUTHORITATIVE
    # rather than trusting the model to echo the pre-computed values — overwrite with the block
    # computed from the fixture's own bars, so a mis-echo (or a gutted canned memo) cannot slip a
    # fabricated trend/level/ADV/abnormal-volume past validation. The model's judgment is the
    # thesis / stance / key_claims, which it still owns.
    memo["technical_block"] = computed

    verification = verify_memo(memo, agent_role=ROLE)

    replay = ReplayTuple(
        trade_id=new_trade_id(), cycle_id=cycle_id, decision_ts=fixture.decision_ts,
        agent_id=ROLE, prompt_version=PROMPT_VERSION, model_version=resp.model_version,
        config_version=manifest.manifest_version, code_version=code_version,
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
    fx = load_fixture(Path("data/fixtures/golden/tech_01_20260701.json"),
                      for_roles=[ROLE], manifest=man)
    run = run_tech_01(
        fixture=fx, candidate="NVDA", client=OpenRouterClient(), manifest=man,
        cycle_id="cycle_20260701_tech", code_version="dev",
    )
    print("=== TECH-01 memo (NVDA) ===")
    print(_json.dumps(run.memo, indent=2)[:2400])
    print("\nVERIF-01 valid:", run.verification.valid,
          "| violations:", run.verification.schema_violations,
          "| stripped:", len(run.verification.stripped_claims))
    print(f"tokens: prompt={run.prompt_tokens} completion={run.completion_tokens} "
          f"| cost_usd=${run.usage_cost_usd:.6f} | model={run.response.model_version}")
    print("replay:", run.replay.to_dict())
