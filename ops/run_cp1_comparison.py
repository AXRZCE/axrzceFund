#!/usr/bin/env python
"""WP3 CP1b — the BULL-seat comparison (rubric docs/wp3-cp1-rubric.md). REAL metered calls, $15 cap.

For each (golden-day, ticker) cell, each of the 3 compared models writes a bull-case ResearchMemo
grounded ONLY in that fixture; the family-disjoint OpenAI judge scores the 3 anonymized memos (masked,
order randomized on a deterministic per-cell seed). We aggregate per-model mean_composite,
schema_valid_rate, grounding_mean, tokens+cost, apply the §5 bar UNCHANGED, and record the seat verdict.

Instrumented for the CP1b completion contract:
  - per-model tokens + USD (usage_by_model);
  - every memo + judge call REPLAY-STAMPED incl. manifest_version -> results/wp3_cp1/replay_stamps.jsonl
    (stored decision records; vendor-free);
  - each fixture's content_hash verified against its committed lock before use (R1).
Full memo text (quotes licensed figures) -> gitignored scratch dir, NOT committed. Hard cap $15;
degrade stop $12 (stop launching new cells, finalize on completed cells).
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from pathlib import Path

from pydantic import ValidationError

from core.agent_output import safe_agent_output_dir
from core.config import load_config
from core.llm import LLMError, OpenRouterClient
from core.manifest import load_manifest
from core.replay import ReplayTuple, new_trade_id
from data.fixtures.harness import DEFAULT_FIXTURE_DIR, Fixture, load_fixture
from graphs.agents.fund_tech import _candidate_doc_block
from graphs.state import ResearchMemo

TICKERS = ["AVGO", "COST", "MDT", "LULU"]
DAYS = ["20260623", "20260624", "20260625", "20260626"]
MODELS = ["BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM", "BULL-01-BASELINE-WEST"]
JUDGE = "VERIF-CP1-JUDGE"
HARD_CAP, DEGRADE_STOP = 15.0, 12.0
BAR_ABS, PARITY, SCHEMA_MIN = 0.70, 0.05, 0.90
OUT = Path("results/wp3_cp1/run3")            # run3 = the RUN OF RECORD (run1 discarded, run2 diagnostic)
C3_PATH = Path("results/wp3_cp1/c3_probe.json")  # C3 already passed + committed — NOT re-run
# Agent memos quote licensed figures -> resolve to a gitignored dir, fail-closed (WP3 CP1b guard 8a).
MEMO_DIR = safe_agent_output_dir(os.environ.get("CP1_MEMO_DIR"), fallback="var/cp1_memos/run3")

# Cumulative-spend discipline: the $12 degrade / $15 cap apply to the WHOLE CP1b effort, not this
# process alone. Prior spend: C3 $0.011 + run1 ~$0.40 (discarded) + run2 $0.9405.
PRIOR_SPEND_USD = 1.352

# DeepSeek-on-Fireworks rate-limit mitigation (run2: 15/16 transport failures; the single spaced C3
# call succeeded): pace the calls and lengthen the client's bounded backoff. Residual failures still
# fail closed and count toward the >=25%-transport => INCOMPLETE contingency rule.
PACING_S = {"BULL-01-CAND-DEEPSEEK": 5.0}
RETRY_KW = {"BULL-01-CAND-DEEPSEEK": {"max_retries": 3, "backoff_s": 6.0}}

BULL_SYS = (
    "You are BULL-01, an adversarial BULL-case equity researcher. Given ONLY the point-in-time data "
    "block for one candidate (as-of decision_ts), construct the STRONGEST HONEST bull case as a JSON "
    "ResearchMemo. Every factual claim MUST cite a doc_id from the data block in its `evidence` list — "
    "do NOT invent numbers. Address at least one real risk honestly. Output ONLY this JSON schema:\n"
    '{"agent_id": str, "ticker": str, "stance": "long", "conviction": 0.0-1.0, "horizon_days": int, '
    '"thesis": str (<=150 words, falsifiable), "key_claims": [{"claim": str, "evidence": [doc_id], '
    '"claim_type": "fact"|"inference"|"estimate"}] (3 to 7 items), "catalysts": [{"event": str, '
    '"expected_window": str}], "invalidation_conditions": [str], "risks": [str], '
    '"what_would_change_my_mind": str}'
)
JUDGE_SYS = (
    "You are VERIF-CP1-JUDGE, an impartial evaluator. You see up to 3 ANONYMIZED bull-case memos "
    "(labelled A/B/C) for the same candidate plus the SAME point-in-time data block they were given. "
    "Score EACH memo on four integer 0-4 dimensions: D1 grounding/citation-fidelity (claims cite "
    "doc_ids present in the data block; uses the block's actual figures; no fabricated numbers); D2 "
    "financial-reasoning quality; D3 thesis coherence & falsifiability; D4 argument specificity & "
    "non-triviality (must engage >=1 real risk). Do NOT reward length or eloquence. Judge only the "
    'memos present. Output ONLY JSON: {"A": {"D1": int, "D2": int, "D3": int, "D4": int, "note": str}, '
    '"B": {...}, "C": {...}} — include only labels that were shown.'
)

USAGE: dict = {r: {"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
               for r in MODELS + [JUDGE]}
STAMPS: list = []
CODE_VERSION = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
CONFIG_VERSION = load_config().config_version


def _spent() -> float:
    return round(sum(u["cost_usd"] for u in USAGE.values()), 6)


def _metered(client, role, spec, messages, man, cid, decision_ts, *, max_tokens,
             max_retries=2, backoff_s=1.0):
    """One metered call: records per-model usage + a replay stamp (incl. manifest_version)."""
    time.sleep(PACING_S.get(role, 0.0))  # rate-limit pacing (DeepSeek/Fireworks)
    resp = client.call(model_version=spec.model_version, messages=messages, provider=spec.provider,
                       response_format={"type": "json_object"}, max_tokens=max_tokens,
                       max_retries=max_retries, backoff_s=backoff_s)
    u = USAGE[role]
    u["cost_usd"] += resp.usage.cost_usd; u["prompt_tokens"] += resp.usage.prompt_tokens
    u["completion_tokens"] += resp.usage.completion_tokens; u["calls"] += 1
    rt = ReplayTuple(trade_id=new_trade_id(), cycle_id=cid, decision_ts=decision_ts, agent_id=role,
                     prompt_version="cp1b", model_version=resp.model_version,
                     manifest_version=man.manifest_version, config_version=CONFIG_VERSION,
                     code_version=CODE_VERSION)
    STAMPS.append({**rt.to_dict(), "usage": {"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens, "cost_usd": resp.usage.cost_usd}})
    return resp


def _validate(memo: dict) -> tuple[bool, list]:
    """§2.1 schema bar + VERIF-01 strip (uncited fact claims); >30% stripped => fail."""
    try:
        m = ResearchMemo.model_validate(memo)
    except ValidationError as e:
        return False, [f"{x['loc']}:{x['msg']}" for x in e.errors()][:5]
    total = len(m.key_claims)
    kept = [kc for kc in m.key_claims if not (kc.claim_type == "fact" and not kc.evidence)]
    problems = []
    if total and (total - len(kept)) / total > 0.30:
        problems.append(">30% fact claims uncited")
    if not (3 <= len(kept) <= 7):
        problems.append(f"kept key_claims {len(kept)} outside [3,7]")
    if len(m.thesis.split()) > 150:
        problems.append("thesis >150 words")
    return (not problems), problems


def _bull_memo(client, role, spec, ticker, decision_ts, data_block, man, cid) -> tuple[dict | None, bool, int]:
    user = (f"Candidate: {ticker}\ndecision_ts: {decision_ts}\n\n{data_block}\n\n"
            f"Produce the bull-case ResearchMemo JSON for {ticker}.")
    memo, ok, retries, reason = None, False, 0, "none"
    for attempt in range(2):  # one retry (P2)
        resp = _metered(client, role, spec, [{"role": "system", "content": BULL_SYS},
                        {"role": "user", "content": user}], man, cid, decision_ts, max_tokens=4096,
                        **RETRY_KW.get(role, {}))
        if attempt == 1:
            retries = 1
        if resp.finish_reason == "length":     # truncated -> not a real schema failure; retry
            reason = "truncated(max_tokens)"; continue
        s = resp.text.find("{")
        if s == -1:
            reason = "no_json"; continue
        try:
            cand, _ = json.JSONDecoder().raw_decode(resp.text[s:])
        except Exception:
            reason = "unparseable_json"; continue
        cand.setdefault("agent_id", "BULL-01"); cand.setdefault("ticker", ticker)
        ok, probs = _validate(cand); memo = cand
        reason = "ok" if ok else ("schema_fail:" + ";".join(probs))
        if ok:
            break
    return memo, ok, retries, reason


def _judge(client, spec, ticker, data_block, labelled, man, cid, decision_ts) -> dict:
    blocks = "\n\n".join(f"=== MEMO {lab} ===\n{json.dumps(m)}" for lab, m in labelled.items())
    user = (f"Candidate: {ticker}\n\n--- POINT-IN-TIME DATA BLOCK ---\n{data_block}\n\n"
            f"--- MEMOS TO SCORE ---\n{blocks}\n\nScore each present memo per the rubric. JSON only.")
    resp = _metered(client, JUDGE, spec, [{"role": "system", "content": JUDGE_SYS},
                    {"role": "user", "content": user}], man, cid, decision_ts, max_tokens=1200)
    s = resp.text.find("{")
    try:
        obj, _ = json.JSONDecoder().raw_decode(resp.text[s:])
    except Exception:
        obj = {}
    return obj


def main() -> None:
    man = load_manifest()
    client = OpenRouterClient()
    MEMO_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    disq = _load_c3_disqualified()

    fixtures: dict[str, Fixture] = {}
    hash_ok: dict[str, bool] = {}
    for d in DAYS:
        fid = f"wp3_cp1_{d}"
        fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{fid}.json", for_roles=MODELS, manifest=man)
        lock = json.loads(Path(f"data/fixtures/locks/{fid}.lock.json").read_text())
        hash_ok[fid] = (fx.content_hash == lock["content_hash"])
        assert hash_ok[fid], f"{fid}: content_hash != committed lock"
        fixtures[d] = fx

    per_cell, incomplete = [], {r: 0 for r in MODELS}
    fail_reasons = {r: {} for r in MODELS}
    for d in DAYS:
        for t in TICKERS:
            if PRIOR_SPEND_USD + _spent() >= DEGRADE_STOP:   # degrade on the CUMULATIVE figure
                print(f"DEGRADE STOP: cumulative ${PRIOR_SPEND_USD + _spent():.4f} >= ${DEGRADE_STOP} "
                      f"— finalizing on completed cells")
                break
            fx = fixtures[d]
            data_block, _doc_ids = _candidate_doc_block(fx, t)
            cid = f"cp1_{d}_{t}"
            memos, oks, retried, reasons = {}, {}, {}, {}
            for role in MODELS:
                if role in disq:
                    continue
                try:
                    memo, ok, rt, reason = _bull_memo(client, role, man.resolve(role), t,
                                                      fx.decision_ts, data_block, man, cid)
                except LLMError as e:
                    memo, ok, rt = None, False, 0
                    reason = "transport:" + str(e)[:200]   # capture the actual error text (run2 gap)
                    incomplete[role] += 1
                    print(f"  {role} failed-closed: {str(e)[:100]}")
                memos[role], oks[role], retried[role], reasons[role] = memo, ok, rt, reason
                key = reason.split(":")[0]
                fail_reasons[role][key] = fail_reasons[role].get(key, 0) + 1
                (MEMO_DIR / f"{d}_{t}_{role}.json").write_text(json.dumps(memo or {}, indent=2))
            seed = int.from_bytes((fx.fixture_id + t).encode(), "big") % (2**31)
            rng = random.Random(seed)
            scored_roles = [r for r in MODELS if oks.get(r)]
            rng.shuffle(scored_roles)
            labels = ["A", "B", "C"][: len(scored_roles)]
            lab2role = dict(zip(labels, scored_roles))
            labelled = {lab: memos[lab2role[lab]] for lab in labels}
            try:
                scores = _judge(client, man.resolve(JUDGE), t, data_block, labelled, man, cid,
                                fx.decision_ts) if labelled else {}
            except LLMError as e:
                scores = {}; print(f"  judge failed-closed: {str(e)[:100]}")
            cell = {"day": d, "ticker": t, "schema_ok": oks, "retried": retried,
                    "lab2role": lab2role, "n_judged_together": len(lab2role), "scores": {},
                    "fail_detail": {r: reasons[r] for r in reasons if not oks.get(r)}}
            for lab, role in lab2role.items():
                sc = scores.get(lab) or {}
                dims = [sc.get(k) for k in ("D1", "D2", "D3", "D4")]
                if all(isinstance(x, (int, float)) for x in dims):
                    cell["scores"][role] = {"D1": dims[0], "D2": dims[1], "D3": dims[2], "D4": dims[3],
                                            "composite": round(sum(dims) / 16.0, 4)}
            per_cell.append(cell)
            print(f"cell {d}/{t}: judged_together={len(lab2role)} scored={list(cell['scores'])} "
                  f"run3=${_spent():.4f} cumulative=${PRIOR_SPEND_USD + _spent():.4f}")
        else:
            continue
        break

    report = _aggregate_and_verdict(per_cell, disq, man, incomplete)
    report.update(run="run3 (run of record)", total_cost_usd=_spent(),
                  prior_spend_usd=PRIOR_SPEND_USD,
                  cumulative_cost_usd=round(PRIOR_SPEND_USD + _spent(), 6),
                  hard_cap_usd=HARD_CAP, degrade_stop_usd=DEGRADE_STOP,
                  cells_completed=len(per_cell), usage_by_model=USAGE,
                  fixture_hash_verified=hash_ok, incomplete_cells=incomplete, fail_reasons=fail_reasons,
                  manifest_version=man.manifest_version, code_version=CODE_VERSION,
                  per_cell=per_cell)
    (OUT / "comparison.json").write_text(json.dumps(report, indent=2))
    with (OUT / "replay_stamps.jsonl").open("w") as f:
        for s in STAMPS:
            f.write(json.dumps(s) + "\n")
    print("\n=== VERDICT ===")
    print(json.dumps(report["verdict"], indent=2))
    print(f"total spend = ${report['total_cost_usd']:.4f} / ${HARD_CAP} cap  | stamps={len(STAMPS)} "
          f"(all carry manifest_version={man.manifest_version})")


def _load_c3_disqualified() -> set:
    if not C3_PATH.exists():
        return set()
    return {r for r, m in json.loads(C3_PATH.read_text()).get("models", {}).items() if m.get("disqualified")}


YIELD_MIN = 0.90  # a model must produce scorable memos in >=90% of cells to be a valid data point


def _aggregate_and_verdict(per_cell, disq, man, incomplete) -> dict:
    n_cells = len(per_cell)
    agg = {}
    for role in MODELS:
        comps, grounds, valid = [], [], 0
        for c in per_cell:
            if role in c["scores"]:
                comps.append(c["scores"][role]["composite"]); grounds.append(c["scores"][role]["D1"])
            if c["schema_ok"].get(role):
                valid += 1
        transport = incomplete.get(role, 0)
        n_scored = len(comps)
        if transport >= 0.25 * n_cells:
            status = "INCOMPLETE_TRANSPORT"
        elif n_scored < YIELD_MIN * n_cells:
            status = "INVALID_LOWYIELD"
        else:
            status = "OK"
        agg[role] = {
            "status": status, "disqualified_c3": role in disq,
            "mean_composite": round(sum(comps) / n_scored, 4) if comps else 0.0,
            "grounding_mean": round(sum(grounds) / n_scored, 4) if grounds else 0.0,
            "schema_valid_rate": round(valid / n_cells, 4) if n_cells else 0.0,
            "n_scored": n_scored, "transport_failures": transport,
            "cost_usd": round(USAGE[role]["cost_usd"], 6),
            "tokens": {"prompt": USAGE[role]["prompt_tokens"], "completion": USAGE[role]["completion_tokens"]},
        }

    west = agg["BULL-01-BASELINE-WEST"]
    # A seat verdict REQUIRES a valid Western baseline — else the G3 parity gate is meaningless.
    if west["status"] != "OK":
        verdict = {"outcome": "INCONCLUSIVE",
                   "reason": f"no valid Western baseline: BULL-01-BASELINE-WEST status={west['status']} "
                             f"(n_scored={west['n_scored']}/{n_cells}, transport_failures="
                             f"{west['transport_failures']}). The G3 parity gate cannot be evaluated, so "
                             f"NO seat can be awarded. Do not seat. Akshar decides rerun-vs-verdict.",
                   "bull_seat": None,
                   "model_status": {r: agg[r]["status"] for r in MODELS}}
        return {"bar_as_declared": {"G1_schema_min": SCHEMA_MIN, "G2_abs_floor": BAR_ABS,
                "G3_parity_margin": PARITY, "west_baseline_mean": west["mean_composite"],
                "west_baseline_status": west["status"]}, "per_model": agg, "verdict": verdict}

    passers = []
    for role in ("BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM"):
        a = agg[role]
        if a["status"] != "OK":
            a["gates"] = {"status": a["status"], "passes": False}
            continue
        g1, g2, g3 = a["schema_valid_rate"] >= SCHEMA_MIN, a["mean_composite"] >= BAR_ABS, \
            a["mean_composite"] >= west["mean_composite"] - PARITY
        a["gates"] = {"G1_schema>=0.90": g1, "G2_mean>=0.70": g2, "G3_parity>=west-0.05": g3,
                      "passes": bool(g1 and g2 and g3 and not a["disqualified_c3"])}
        if a["gates"]["passes"]:
            passers.append(role)
    incomplete_cands = [r for r in ("BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM") if agg[r]["status"] != "OK"]
    if passers:
        winner = max(passers, key=lambda r: (agg[r]["mean_composite"], agg[r]["schema_valid_rate"],
                                             agg[r]["grounding_mean"]))
        verdict = {"outcome": "SEAT_CHINESE", "bull_seat": winner,
                   "model_version": man.resolve(winner).model_version,
                   "reason": f"{winner} clears G1-G3 vs a valid baseline "
                             f"(mean={agg[winner]['mean_composite']}, west={west['mean_composite']})",
                   "caveat": (f"candidate(s) {incomplete_cands} were incomplete; the absolute bar is met "
                              f"regardless, but the tie-break vs them could not be run") if incomplete_cands else None}
    elif incomplete_cands:
        verdict = {"outcome": "INCONCLUSIVE", "bull_seat": None,
                   "reason": f"no candidate passed AND candidate(s) {incomplete_cands} incomplete — cannot "
                             f"conclude; Akshar decides rerun-vs-verdict."}
    else:
        verdict = {"outcome": "FALLBACK_WEST_GROK", "bull_seat": "xAI Grok (pre-committed §7 addendum)",
                   "reason": f"both Chinese candidates complete but neither cleared the §5 bar vs the valid "
                             f"baseline (west mean={west['mean_composite']}); fallback = xAI Grok."}
    return {"bar_as_declared": {"G1_schema_min": SCHEMA_MIN, "G2_abs_floor": BAR_ABS,
            "G3_parity_margin": PARITY, "west_baseline_mean": west["mean_composite"],
            "west_baseline_status": west["status"]}, "per_model": agg, "verdict": verdict}


if __name__ == "__main__":
    main()
