#!/usr/bin/env python
"""WP3 CP4 E2E smoke — the COMPLETE WP3 pipeline. PAID, $3 hard cap.

memo → VERIF-01 → 3-family debate → **T3 judge scores the debate (R6: family resolved at call
time, disjoint from both debaters)** → sealed votes → tally → PM-01 → TradeProposal, with
**shadow voters logged alongside (R7)** and the decorrelation metric computed from the logs.
Golden day 2026-06-26 / COST — the last unused day and sector (Staples) for spread.

Artifact: results/wp3_cp4/full_smoke.json. Memo body → gitignored var/; vendor scan gates the write.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.agent_output import safe_agent_output_dir
from core.config import param_number
from core.event_log import EventLog
from core.llm import OpenRouterClient
from core.manifest import load_manifest
from data.fixtures.harness import DEFAULT_FIXTURE_DIR, adv_usd_20d, load_fixture
from graphs.agents.fund_tech import run_fund_tech
from graphs.ballot import tally
from graphs.debate import cast_votes, preflight, run_debate
from graphs.judge import run_judge_debate
from graphs.pm import reconstruct_decision, run_pm
from graphs.shadow import compute_decorrelation, run_shadow_votes

FIXTURE_ID = "wp3_cp1_20260626"
CANDIDATE = "COST"
HARD_CAP = 3.0
PRIOR_CUMULATIVE = 3.575  # honest ledger through CP3 (docs/wp3-cp3-readout.md)
OUT = Path("results/wp3_cp4")
MEMO_DIR = safe_agent_output_dir(None, fallback="var/cp4_smoke")
ROLES = ["BULL-01", "BEAR-01", "MOD-01", "PM-01", "FUND-TECH",
         "VERIF-01-JUDGE-GOOGLE", "BULL-01-CAND-DEEPSEEK", "BULL-01-BASELINE-WEST"]


def _cap(spent: float, stage: str) -> None:
    if spent >= HARD_CAP:
        raise RuntimeError(f"$3 smoke cap reached at {stage} (${spent:.4f}) — aborting")


def main() -> None:
    man = load_manifest()
    client = OpenRouterClient()
    preflight(man)
    code_version = "cp4-smoke"

    fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{FIXTURE_ID}.json", for_roles=ROLES, manifest=man)
    lock = json.loads(Path(f"data/fixtures/locks/{FIXTURE_ID}.lock.json").read_text())
    assert fx.content_hash == lock["content_hash"], "fixture hash != committed lock"

    spent = 0.0
    cycle_id = f"cp4_smoke_{FIXTURE_ID}_{CANDIDATE}"
    el = EventLog(Path("var/cp4_smoke_event_log.db"))

    # 1) memo → VERIF-01
    run = run_fund_tech(fixture=fx, candidate=CANDIDATE, client=client, manifest=man,
                        cycle_id=cycle_id, code_version=code_version)
    spent += run.usage_cost_usd
    _cap(spent, "post-memo")
    if not run.verification.valid:
        raise RuntimeError(f"memo failed VERIF-01: {run.verification.schema_violations}")
    (MEMO_DIR / f"{cycle_id}_FUND-TECH.json").write_text(json.dumps(run.memo, indent=2))
    verified = [run.memo]

    # 2) debate
    result = run_debate(candidate=CANDIDATE, verified_memos=verified, client=client, manifest=man,
                        cycle_id=cycle_id, decision_ts=fx.decision_ts, code_version=code_version)
    spent += result.cost_usd
    _cap(spent, "post-debate")

    # 3) R6 — judge the debate: judged families = {BULL(chinese), BEAR(openai)} → judge resolves
    #    to the disjoint family (google) AT CALL TIME; masked + seed-randomized; grounding-checked.
    judged = {man.resolve_runtime("BULL-01").family, man.resolve_runtime("BEAR-01").family}
    judge = run_judge_debate(turns=result.turns, verified_memos=verified, judged_families=judged,
                             client=client, manifest=man, cycle_id=cycle_id,
                             decision_ts=fx.decision_ts, code_version=code_version,
                             seed_key=f"{FIXTURE_ID}:{CANDIDATE}")
    spent += judge.cost_usd
    _cap(spent, "post-judge")

    # 4) votes → tally → PM-01
    ballots, vote_stamps, vote_cost = cast_votes(
        candidate=CANDIDATE, verified_memos=verified, result=result, research_voters=["FUND-TECH"],
        client=client, manifest=man, cycle_id=cycle_id, decision_ts=fx.decision_ts,
        code_version=code_version)
    spent += vote_cost
    summary, direction = tally(ballots, margin_threshold=param_number("ballot_margin_threshold"))
    pm = run_pm(candidate=CANDIDATE, verified_memos=verified, debate_summary=result.summary,
                premortem_top_risks=result.premortem_top_risks, ballot_summary=summary,
                ballot_direction=direction, debate_failed=False, client=client, manifest=man,
                cycle_id=cycle_id, decision_ts=fx.decision_ts, code_version=code_version,
                nav_usd=1_000_000, adv_usd_20d=adv_usd_20d(fx, CANDIDATE),
                event_log=el, prior_overrides_this_month=0)
    spent += pm.cost_usd
    _cap(spent, "post-pm")
    replayed = reconstruct_decision(el, cycle_id)
    assert replayed is not None
    if pm.action == "trade":
        assert replayed["proposal"] == pm.proposal.model_dump(), "replay != stored decision"

    # 5) R7 — shadows logged AFTER the live decision is made; decorrelation computed from the logs
    shadows, shadow_cost = run_shadow_votes(
        verified_memos=verified, debate_summary_json=result.summary.model_dump_json(),
        client=client, manifest=man, cycle_id=cycle_id, decision_ts=fx.decision_ts,
        code_version=code_version, event_log=el)
    spent += shadow_cost
    _cap(spent, "post-shadow")
    live_stances = {f"{b.voter}({man.resolve(b.voter).family})": b.stance for b in ballots}
    decorrelation = compute_decorrelation(live_stances, shadows)

    artifact = {
        "cycle_id": cycle_id, "fixture_id": FIXTURE_ID, "candidate": CANDIDATE,
        "fixture_hash_verified": True, "content_hash": fx.content_hash,
        "manifest_version": man.manifest_version,
        "ballot": {"votes": [b.model_dump() for b in ballots], "summary": summary.model_dump(),
                   "direction": direction},
        "judge": {"family": judge.judge_family, "role": judge.judge_role,
                  "judged_families": sorted(judged), "scores": judge.scores.model_dump()},
        "pm_decision": {"action": pm.action,
                        "proposal": pm.proposal.model_dump() if pm.proposal else None,
                        "no_trade": pm.no_trade, "is_override": pm.is_override,
                        "sizing_audit": pm.sizing_audit},
        "replay_check": {"reconstructed_equals_stored": True, "reads_event_log_only": True},
        "shadow": {"votes": [{"role": v.role, "family": v.family, "stance": v.stance,
                              "conviction": v.conviction} for v in shadows],
                   "decorrelation": decorrelation,
                   "isolation": "structural — graphs/shadow.py imports no live-state module "
                                "(AST-scanned test); shadows ran AFTER the live decision"},
        "replay_stamps": [
            {**run.replay.to_dict(), "usage": {"cost_usd": run.usage_cost_usd}},
            *result.stamps, judge.stamp, *vote_stamps, pm.stamp, *[v.stamp for v in shadows],
        ],
        "spend": {"smoke_usd": round(spent, 6), "cap_usd": HARD_CAP,
                  "cumulative_ledger_usd": round(PRIOR_CUMULATIVE + spent, 4)},
    }
    blob = json.dumps(artifact)
    for marker in ('"price_bars"', '"pit_grade"'):
        assert marker not in blob, f"licensed row marker {marker} in artifact"
    from ops.precommit_guard import is_vendor_data
    assert is_vendor_data("results/wp3_cp4/full_smoke.json", blob.encode()) is None

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "full_smoke.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({
        "ballot": summary.model_dump(), "direction": direction,
        "judge": {"family": judge.judge_family,
                  "bull": judge.scores.bull.model_dump(exclude={"claims_scored"}),
                  "bear": judge.scores.bear.model_dump(exclude={"claims_scored"})},
        "pm": {"action": pm.action,
               "size": pm.proposal.size_pct_nav if pm.proposal else None,
               "direction": pm.proposal.direction if pm.proposal else None,
               "audit": pm.sizing_audit},
        "shadow": [(v.role, v.stance, v.conviction) for v in shadows],
        "decorrelation_rate": decorrelation["stance_agreement_rate"],
        "smoke_usd": round(spent, 6), "cumulative": round(PRIOR_CUMULATIVE + spent, 4),
    }, indent=2))


if __name__ == "__main__":
    main()
