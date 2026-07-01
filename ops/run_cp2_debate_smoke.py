#!/usr/bin/env python
"""WP3 CP2 E2E debate smoke — the first time three families argue. PAID, $3 hard cap.

ONE full debate cycle on ONE hash-verified CP1 golden-day fixture through the LIVE roster
(BULL-01 = z-ai/glm-5.2 [chinese/together], BEAR-01 = openai/gpt-5.4, MOD-01 = gemini-3.1-pro):
real FUND-TECH memo → VERIF-01 validation → P4 debate (rounds ≤ 3, closings, MOD neutral summary)
→ P5 sealed votes (BULL/BEAR constitutionally fixed) → computed ballot_summary (graphs/ballot.tally).

Metered + replay-stamped (manifest_version) throughout. The committed artifact
(results/wp3_cp2/debate_smoke.json) carries the transcript/votes/ballot/stamps/spend — our own
output; the memo body (quotes licensed figures) stays in gitignored var/. A vendor-data scan runs
before the artifact is written; licensed ROW data never enters it.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.agent_output import safe_agent_output_dir
from core.config import param_number
from core.llm import OpenRouterClient
from core.manifest import load_manifest
from data.fixtures.harness import DEFAULT_FIXTURE_DIR, load_fixture
from graphs.agents.fund_tech import run_fund_tech
from graphs.ballot import tally
from graphs.debate import cast_votes, preflight, run_debate

FIXTURE_ID = "wp3_cp1_20260624"
CANDIDATE = "AVGO"
HARD_CAP = 3.0
PRIOR_CUMULATIVE = 2.5193  # C3 + run1 + run2 + run3 (docs/wp3-cp1-comparison.md §5&7)
OUT = Path("results/wp3_cp2")
MEMO_DIR = safe_agent_output_dir(None, fallback="var/cp2_smoke")  # licensed-figure quoting → gitignored
ROLES = ["BULL-01", "BEAR-01", "MOD-01", "FUND-TECH"]


def _cap(spent: float, stage: str) -> None:
    if spent >= HARD_CAP:
        raise RuntimeError(f"$3 smoke cap reached at {stage} (${spent:.4f}) — aborting (never exceed)")


def main() -> None:
    man = load_manifest()
    client = OpenRouterClient()
    preflight(man)  # heterogeneity + runtime scope, fail-closed before any spend
    code_version = "cp2-smoke"

    # fixture: R1 gate + committed-lock hash verification
    fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{FIXTURE_ID}.json", for_roles=ROLES, manifest=man)
    lock = json.loads(Path(f"data/fixtures/locks/{FIXTURE_ID}.lock.json").read_text())
    assert fx.content_hash == lock["content_hash"], "fixture hash != committed lock"

    spent = 0.0
    cycle_id = f"cp2_smoke_{FIXTURE_ID}_{CANDIDATE}"

    # 1) real research memo (FUND-TECH, WP2 agent) → VERIF-01 validation
    run = run_fund_tech(fixture=fx, candidate=CANDIDATE, client=client, manifest=man,
                        cycle_id=cycle_id, code_version=code_version)
    spent += run.usage_cost_usd
    _cap(spent, "post-memo")
    if not run.verification.valid:
        raise RuntimeError(f"FUND-TECH memo failed VERIF-01: {run.verification.schema_violations}")
    (MEMO_DIR / f"{cycle_id}_FUND-TECH.json").write_text(json.dumps(run.memo, indent=2))
    verified_memos = [run.memo]

    # 2) P4 debate — three families, rounds ≤ max_debate_rounds, integrity-checked in code
    result = run_debate(candidate=CANDIDATE, verified_memos=verified_memos, client=client,
                        manifest=man, cycle_id=cycle_id, decision_ts=fx.decision_ts,
                        code_version=code_version)
    spent += result.cost_usd
    _cap(spent, "post-debate")

    # 3) P5 sealed votes → computed ballot_summary
    ballots, vote_stamps, vote_cost = cast_votes(
        candidate=CANDIDATE, verified_memos=verified_memos, result=result,
        research_voters=["FUND-TECH"], client=client, manifest=man,
        cycle_id=cycle_id, decision_ts=fx.decision_ts, code_version=code_version)
    spent += vote_cost
    _cap(spent, "post-votes")
    summary, direction = tally(ballots, margin_threshold=param_number("ballot_margin_threshold"))

    artifact = {
        "cycle_id": cycle_id, "fixture_id": FIXTURE_ID, "candidate": CANDIDATE,
        "fixture_hash_verified": True, "content_hash": fx.content_hash,
        "manifest_version": man.manifest_version,
        "roster": {r: man.resolve(r).model_version for r in ("BULL-01", "BEAR-01", "MOD-01")},
        "memo_verification": {"valid": run.verification.valid,
                              "stripped_claims": len(run.verification.stripped_claims)},
        "transcript": {
            "turns": [t.model_dump() for t in result.turns],
            "closings": [c.model_dump() for c in result.closings],
            "mod_summary": result.summary.model_dump(),
        },
        "votes": [b.model_dump() for b in ballots],
        "ballot_summary": summary.model_dump(),
        "winning_direction": direction,
        "replay_stamps": [ *__memo_stamp(run), *result.stamps, *vote_stamps ],
        "spend": {"smoke_usd": round(spent, 6), "cap_usd": HARD_CAP,
                  "cumulative_usd": round(PRIOR_CUMULATIVE + spent, 6)},
    }

    # vendor-safety: no licensed ROW data may enter the committed artifact
    blob = json.dumps(artifact)
    for row_marker in ('"price_bars"', '"fundamentals"', '"available_at"', '"pit_grade"'):
        assert row_marker not in blob, f"licensed row marker {row_marker} in artifact — refusing"
    from ops.precommit_guard import is_vendor_data
    assert is_vendor_data("results/wp3_cp2/debate_smoke.json", blob.encode()) is None

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "debate_smoke.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({
        "turns": len(result.turns), "closings": len(result.closings),
        "cruxes": result.summary.unresolved_cruxes,
        "votes": [(b.voter, b.stance, b.conviction) for b in ballots],
        "ballot_summary": summary.model_dump(), "direction": direction,
        "smoke_usd": round(spent, 6), "cumulative_usd": round(PRIOR_CUMULATIVE + spent, 6),
    }, indent=2))


def __memo_stamp(run) -> list[dict]:
    return [{**run.replay.to_dict(), "usage": {"prompt_tokens": run.prompt_tokens,
             "completion_tokens": run.completion_tokens, "cost_usd": run.usage_cost_usd}}]


if __name__ == "__main__":
    main()
