#!/usr/bin/env python
"""WP3 CP1b — C3 memorization probe (rubric §5, MANDATORY, runs FIRST). REAL metered calls.

For each compared model, with NO fixture provided, elicit its best estimate of the closing prices it
should not know (post-availability golden window), compare to the pit_store actuals (±1%), and compute
a hit-rate. Disqualify a model whose hit-rate > 0.25 (refusals/nulls count as non-hits).

Honest-by-construction: the metered client is FAIL-CLOSED. If a pinned model/host is not servable, the
call raises LLMError and this script records the error for that model — it never fabricates a result.
Records only hit-rates / stated-vs-hit / cost (NOT the licensed actual closes) to results/wp3_cp1/.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.llm import LLMError, OpenRouterClient
from core.manifest import load_manifest
from data.pit_store import PITStore

TICKERS = ["AVGO", "COST", "MDT", "LULU"]
DAYS = ["2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]
CMP_ROLES = ["BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM", "BULL-01-BASELINE-WEST"]
DISQ_THRESHOLD = 0.25
TOL = 0.01
OUT = Path("results/wp3_cp1")

PROMPT = (
    "You have NO access to any external data, tools, or the internet. From your own parametric "
    "knowledge ONLY, give your best estimate of the official U.S. market CLOSING PRICE (USD) for each "
    "ticker on each exact date. Respond with ONLY a JSON object of the form "
    '{"TICKER": {"YYYY-MM-DD": number_or_null}} and nothing else. Use null if you do not know a value.\n'
    f"Tickers: {', '.join(TICKERS)}\nDates: {', '.join(DAYS)}"
)


def _actual_closes(store: PITStore) -> dict:
    closes: dict = {}
    for t in TICKERS:
        for d in DAYS:
            rows = store.get_price_bars([t], as_known_at=f"{d}T23:59:59+00:00")
            same = [r for r in rows if str(r.get("as_of", "")).startswith(d)]
            if same:
                closes[(t, d)] = float(same[-1]["close"])
    return closes


def _parse(text: str) -> dict:
    s = text.find("{")
    if s == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[s:])
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def main() -> None:
    store = PITStore()
    man = load_manifest()
    client = OpenRouterClient()
    actual = _actual_closes(store)
    n_items = len(TICKERS) * len(DAYS)
    OUT.mkdir(parents=True, exist_ok=True)

    results = {"threshold": DISQ_THRESHOLD, "tol": TOL, "n_items": n_items,
               "manifest_version": man.manifest_version, "models": {}}
    for role in CMP_ROLES:
        spec = man.resolve(role)
        entry: dict = {"model_version": spec.model_version, "provider": spec.provider}
        try:
            resp = client.call(model_version=spec.model_version,
                               messages=[{"role": "user", "content": PROMPT}],
                               provider=spec.provider, response_format={"type": "json_object"},
                               max_tokens=800)
            stated = _parse(resp.text)
            hits = 0
            for t in TICKERS:
                for d in DAYS:
                    v = (stated.get(t) or {}).get(d)
                    a = actual.get((t, d))
                    if v is not None and a and abs(float(v) - a) / a <= TOL:
                        hits += 1
            rate = hits / n_items
            entry.update(servable=True, hit_rate=round(rate, 4), hits=hits,
                         disqualified=rate > DISQ_THRESHOLD, cost_usd=resp.usage.cost_usd,
                         model_ran=resp.model_version)
            print(f"{role}: servable  hit_rate={rate:.3f} ({hits}/{n_items})  "
                  f"disq={rate > DISQ_THRESHOLD}  cost=${resp.usage.cost_usd:.6f}")
        except LLMError as e:
            entry.update(servable=False, error=str(e)[:300], cost_usd=0.0)
            print(f"{role}: NOT SERVABLE (fail-closed) — {str(e)[:160]}")
        results["models"][role] = entry

    total = sum(m.get("cost_usd", 0.0) for m in results["models"].values())
    results["total_cost_usd"] = round(total, 6)
    (OUT / "c3_probe.json").write_text(json.dumps(results, indent=2))
    print(f"total C3 spend = ${total:.6f}  -> results/wp3_cp1/c3_probe.json")


if __name__ == "__main__":
    main()
