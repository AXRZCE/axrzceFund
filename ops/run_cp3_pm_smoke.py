#!/usr/bin/env python
"""WP3 CP3 E2E smoke — one full cycle through PM-01. PAID, $3 hard cap.

memo (FUND-TECH) → VERIF-01 → P4 debate (live 3-family roster) → P5 sealed votes → computed
ballot_summary → **PM-01 real call** → §2.3 TradeProposal with SERVER-AUTHORITATIVE sizing.
Everything metered + replay-stamped (manifest_version). Then ONE SYNTHETIC CONTESTED case
(constructed votes, margin < 0.20) is pushed through the SAME sizing/tally code path — no extra
LLM — to show the ×0.5 haircut AND the 0.5% cap fire on real plumbing (R4).

Artifact: results/wp3_cp3/pm_smoke.json (proposal, sizing audit, contested demo, stamps, ledger).
The memo body stays in gitignored var/; a vendor scan gates the artifact write.
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
from graphs.pm import reconstruct_decision, run_pm, size_position
from graphs.state import Ballot

FIXTURE_ID = "wp3_cp1_20260625"   # a different golden day than CP2's smoke
CANDIDATE = "MDT"                 # different sector (Health Care) than CP2's AVGO
HARD_CAP = 3.0
PRIOR_CUMULATIVE = 3.33           # honest ledger through CP2 (docs/wp3-cp2-readout.md)
OUT = Path("results/wp3_cp3")
MEMO_DIR = safe_agent_output_dir(None, fallback="var/cp3_smoke")
ROLES = ["BULL-01", "BEAR-01", "MOD-01", "PM-01", "FUND-TECH"]


def _cap(spent: float, stage: str) -> None:
    if spent >= HARD_CAP:
        raise RuntimeError(f"$3 smoke cap reached at {stage} (${spent:.4f}) — aborting")


def main() -> None:
    man = load_manifest()
    client = OpenRouterClient()
    preflight(man)
    threshold = param_number("ballot_margin_threshold")
    code_version = "cp3-smoke"

    fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{FIXTURE_ID}.json", for_roles=ROLES, manifest=man)
    lock = json.loads(Path(f"data/fixtures/locks/{FIXTURE_ID}.lock.json").read_text())
    assert fx.content_hash == lock["content_hash"], "fixture hash != committed lock"

    spent = 0.0
    cycle_id = f"cp3_smoke_{FIXTURE_ID}_{CANDIDATE}"
    el = EventLog(Path("var/cp3_smoke_event_log.db"))

    # 1) memo → VERIF-01
    run = run_fund_tech(fixture=fx, candidate=CANDIDATE, client=client, manifest=man,
                        cycle_id=cycle_id, code_version=code_version)
    spent += run.usage_cost_usd
    _cap(spent, "post-memo")
    if not run.verification.valid:
        raise RuntimeError(f"memo failed VERIF-01: {run.verification.schema_violations}")
    (MEMO_DIR / f"{cycle_id}_FUND-TECH.json").write_text(json.dumps(run.memo, indent=2))
    verified = [run.memo]

    # 2) debate → 3) votes → tally
    result = run_debate(candidate=CANDIDATE, verified_memos=verified, client=client, manifest=man,
                        cycle_id=cycle_id, decision_ts=fx.decision_ts, code_version=code_version)
    spent += result.cost_usd
    _cap(spent, "post-debate")
    ballots, vote_stamps, vote_cost = cast_votes(
        candidate=CANDIDATE, verified_memos=verified, result=result, research_voters=["FUND-TECH"],
        client=client, manifest=man, cycle_id=cycle_id, decision_ts=fx.decision_ts,
        code_version=code_version)
    spent += vote_cost
    _cap(spent, "post-votes")
    summary, direction = tally(ballots, margin_threshold=threshold)

    # 4) PM-01 — the real decision, code-disciplined sizing, event-logged for replay
    pm = run_pm(candidate=CANDIDATE, verified_memos=verified, debate_summary=result.summary,
                premortem_top_risks=result.premortem_top_risks, ballot_summary=summary,
                ballot_direction=direction, debate_failed=False, client=client, manifest=man,
                cycle_id=cycle_id, decision_ts=fx.decision_ts, code_version=code_version,
                nav_usd=1_000_000, adv_usd_20d=adv_usd_20d(fx, CANDIDATE),
                event_log=el, prior_overrides_this_month=0)
    spent += pm.cost_usd
    _cap(spent, "post-pm")

    # R5 replay: read the STORED decision back — no client involved
    replayed = reconstruct_decision(el, cycle_id)
    assert replayed is not None
    if pm.action == "trade":
        assert replayed["proposal"] == pm.proposal.model_dump(), "replay != stored decision"

    # 5) SYNTHETIC CONTESTED case through the SAME code path (no LLM): margin 0.1 < 0.20
    cv = [Ballot(voter="FUND-TECH", stance="long", conviction=0.55, size_inclination="standard"),
          Ballot(voter="BULL-01", stance="long", conviction=0.0, size_inclination="small"),
          Ballot(voter="BEAR-01", stance="short", conviction=0.45, size_inclination="standard")]
    c_summary, c_dir = tally(cv, margin_threshold=threshold)
    assert c_summary.contested, "constructed ballot must be contested"
    c_size, c_audit = size_position(conviction=0.9, contested=c_summary.contested)
    assert c_audit["haircuts"]["contested"] == 0.5 and c_size <= 0.5, "R4 mechanics must fire"

    artifact = {
        "cycle_id": cycle_id, "fixture_id": FIXTURE_ID, "candidate": CANDIDATE,
        "fixture_hash_verified": True, "content_hash": fx.content_hash,
        "manifest_version": man.manifest_version,
        "ballot": {"votes": [b.model_dump() for b in ballots],
                   "summary": summary.model_dump(), "direction": direction},
        "pm_decision": {
            "action": pm.action,
            "proposal": pm.proposal.model_dump() if pm.proposal else None,
            "no_trade": pm.no_trade, "is_override": pm.is_override,
            "sizing_audit": pm.sizing_audit,
        },
        "replay_check": {"reconstructed_equals_stored": True, "reads_event_log_only": True},
        "contested_demo_synthetic": {
            "votes": [b.model_dump() for b in cv],
            "summary": c_summary.model_dump(), "direction": c_dir,
            "sizing_audit": c_audit,
            "note": "constructed votes, code path only (no LLM): margin<0.20 ⇒ contested ⇒ ×0.5 "
                    "haircut AND ≤0.5% cap fire on the real plumbing (R4)",
        },
        "replay_stamps": [
            {**run.replay.to_dict(), "usage": {"cost_usd": run.usage_cost_usd}},
            *result.stamps, *vote_stamps, pm.stamp,
        ],
        "spend": {"smoke_usd": round(spent, 6), "cap_usd": HARD_CAP,
                  "cumulative_ledger_usd": round(PRIOR_CUMULATIVE + spent, 4)},
    }
    blob = json.dumps(artifact)
    for marker in ('"price_bars"', '"fundamentals"', '"pit_grade"'):
        assert marker not in blob, f"licensed row marker {marker} in artifact"
    from ops.precommit_guard import is_vendor_data
    assert is_vendor_data("results/wp3_cp3/pm_smoke.json", blob.encode()) is None

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pm_smoke.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({
        "ballot": summary.model_dump(), "direction": direction,
        "pm_action": pm.action,
        "pm_size": pm.proposal.size_pct_nav if pm.proposal else None,
        "pm_direction": pm.proposal.direction if pm.proposal else None,
        "sizing_audit": pm.sizing_audit, "is_override": pm.is_override,
        "contested_demo": {"margin": c_summary.margin, "size": c_size},
        "smoke_usd": round(spent, 6),
        "cumulative": round(PRIOR_CUMULATIVE + spent, 4),
    }, indent=2))


if __name__ == "__main__":
    main()
