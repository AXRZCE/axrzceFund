"""FUND-TECH first real agent — end-to-end proof (WP2, live API).

One real Gemini 3.1 Pro call (~$0.04) on the committed golden fixture proves the full chain:
R1 gated, R3 schema-valid + VERIF-01-validated, grounded-in-fixture (cites the fixture's own
doc_ids), R4 real cost recorded in the decision record, R5 replay-stamped.

Anti-hoax: gutting `run_fund_tech` to a canned memo turns this red — a canned return has no real
metered cost (cost>0 fails) and wouldn't cite this fixture's specific doc_ids (grounding fails).
Skipped when no OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from core.event_log import EventLog  # noqa: E402
from core.llm import OpenRouterClient  # noqa: E402
from core.manifest import load_manifest  # noqa: E402
from data.fixtures.harness import load_fixture  # noqa: E402
from graphs.agents.fund_tech import run_fund_tech  # noqa: E402

GOLDEN = Path("data/fixtures/golden/fund_tech_20260624.json")  # gitignored (licensed data)
LOCK = Path("data/fixtures/locks/fund_tech_20260624.lock.json")  # tracked: hash + metadata
CANDIDATE = "BNC"

# integration -> deselected by the default `-m 'not integration'` run (no accidental live call);
# skipif -> also skip-safe when run explicitly without the key or the gitignored fixture.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENROUTER_API_KEY") or not GOLDEN.exists(),
        reason="needs OPENROUTER_API_KEY + the local golden fixture (gitignored, not in fresh clones)",
    ),
]


def test_fund_tech_grounded_validated_metered_replay(tmp_path):
    man = load_manifest()
    fx = load_fixture(GOLDEN, for_roles=["FUND-TECH"], manifest=man)  # R1 gate
    # reproducibility: the local fixture matches the committed lockfile hash (no drift)
    assert fx.content_hash == json.loads(LOCK.read_text())["content_hash"]
    log = EventLog(tmp_path / "ev.db")

    run = run_fund_tech(
        fixture=fx, candidate=CANDIDATE, client=OpenRouterClient(), manifest=man,
        cycle_id="cycle_test", code_version="test", event_log=log,
    )

    # R3 — schema-valid + VERIF-01-validated, with the §3.2 block
    assert run.verification.valid, run.verification.schema_violations
    assert run.memo["ticker"] == CANDIDATE
    assert "valuation_block" in run.memo and "fair_value_range" in run.memo["valuation_block"]
    assert 3 <= len(run.memo["key_claims"]) <= 7

    # Grounded — cites THIS fixture's doc_ids (a fixture-ignoring memo wouldn't)
    cited = {e for kc in run.memo["key_claims"] for e in kc.get("evidence", [])}
    fixture_docs = {
        f"sf1:{CANDIDATE}:{ind}:{r['period']}"
        for ind, rows in fx.payload["fundamentals"].items()
        for r in rows if r.get("ticker") == CANDIDATE
    }
    assert cited & fixture_docs, f"memo cites no fixture doc_id — not grounded (cited={cited})"

    # R4 — real metered cost, recorded into the decision record (event log)
    assert run.usage_cost_usd > 0.0
    assert run.prompt_tokens > 0 and run.completion_tokens > 0
    events = log.get_events(cycle_id="cycle_test", agent_id="FUND-TECH")
    assert events and events[0].event_type == "memo_written"
    assert events[0].payload["usage"]["cost_usd"] > 0.0

    # R5 — replay-stamped (model + manifest version + decision boundary).
    # WP3 R5: manifest hash now lives in its OWN field (was conflated into config_version at WP2).
    assert run.replay.model_version.startswith("google/gemini-3.1-pro")
    assert run.replay.decision_ts == fx.decision_ts
    assert run.replay.manifest_version == man.manifest_version
    assert run.replay.config_version != man.manifest_version  # un-conflated: config_version is configuration.md's hash
