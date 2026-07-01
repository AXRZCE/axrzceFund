"""TECH-01 second real agent — end-to-end proof (WP2, live API).

One real Gemini 2.5 Flash-Lite call (~$0.0004) on the committed TECH-01 golden fixture proves the
full chain: R1 gated, R3 schema-valid + VERIF-01-validated, grounded-in-fixture (cites the
fixture's own `sep:` price doc_ids), R4 real cost recorded in the decision record, R5
replay-stamped.

Anti-hoax: gutting `run_tech_01` to a canned memo turns this red — a canned return has no real
metered cost (cost>0 fails) and wouldn't cite this fixture's specific `sep:` doc_ids (grounding
fails). Deselected by default (marked integration); skipped when no OPENROUTER_API_KEY / no fixture.
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
from graphs.agents.tech_01 import _price_doc_block, run_tech_01  # noqa: E402

GOLDEN = Path("data/fixtures/golden/tech_01_20260701.json")  # gitignored (licensed SEP data)
LOCK = Path("data/fixtures/locks/tech_01_20260701.lock.json")  # tracked: hash + metadata
CANDIDATE = "NVDA"

# integration -> deselected by the default `-m 'not integration'` run (no accidental live call);
# skipif -> also skip-safe when run explicitly without the key or the gitignored fixture.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENROUTER_API_KEY") or not GOLDEN.exists(),
        reason="needs OPENROUTER_API_KEY + the local golden fixture (gitignored, not in fresh clones)",
    ),
]


def test_tech_01_grounded_validated_metered_replay(tmp_path):
    man = load_manifest()
    fx = load_fixture(GOLDEN, for_roles=["TECH-01"], manifest=man)  # R1 gate (TECH-01 cutoff 2025-07-22)
    # reproducibility: the local fixture matches the committed lockfile hash (no drift)
    assert fx.content_hash == json.loads(LOCK.read_text())["content_hash"]
    log = EventLog(tmp_path / "ev.db")

    run = run_tech_01(
        fixture=fx, candidate=CANDIDATE, client=OpenRouterClient(), manifest=man,
        cycle_id="cycle_test", code_version="test", event_log=log,
    )

    # R3 — schema-valid + VERIF-01-validated, with the §3.4 block
    assert run.verification.valid, run.verification.schema_violations
    assert run.memo["ticker"] == CANDIDATE
    tb = run.memo["technical_block"]
    assert tb["trend"] in ("up", "down", "range")
    assert isinstance(tb["abnormal_volume"], bool) and isinstance(tb["key_levels"], list)
    assert isinstance(tb["adv_pct_at_proposed_size"], (int, float))
    assert 3 <= len(run.memo["key_claims"]) <= 7

    # The technical_block is the fixture's OBJECTIVE structure (not model judgment): assert it equals
    # the values recomputed from the fixture's bars. run_tech_01 overwrites it authoritatively, so a
    # gutted canned run (which won't) or a fabricated block goes red here.
    _txt, _anchor_docs, computed = _price_doc_block(fx, CANDIDATE)
    assert tb == computed, f"technical_block is not the fixture's computed structure: {tb} != {computed}"

    # Grounded — the memo's FACT claims cite this fixture's REAL sep: bars: >=2 distinct, and no
    # fabricated dates (every cited sep: doc_id must be an actual bar). A canned memo hardcoding one
    # guessable date, or citing an invented date, goes red.
    fixture_docs = {
        f"sep:{CANDIDATE}:{str(b['as_of'])[:10]}"
        for b in fx.payload["price_bars"]
        if b.get("ticker") == CANDIDATE and b.get("source") == "sep"
    }
    fact_cites = {e for kc in run.memo["key_claims"]
                  if kc.get("claim_type") == "fact" for e in kc.get("evidence", [])}
    sep_cites = {e for e in fact_cites if e.startswith(f"sep:{CANDIDATE}:")}
    assert sep_cites <= fixture_docs, f"fact claim cites a fabricated doc_id: {sep_cites - fixture_docs}"
    assert len(sep_cites) >= 2, f"weak grounding — fact claims cite < 2 real fixture bars: {sep_cites}"

    # R4 — real metered cost, recorded into the decision record (event log)
    assert run.usage_cost_usd > 0.0
    assert run.prompt_tokens > 0 and run.completion_tokens > 0
    events = log.get_events(cycle_id="cycle_test", agent_id="TECH-01")
    assert events and events[0].event_type == "memo_written"
    assert events[0].payload["usage"]["cost_usd"] > 0.0

    # R5 — replay-stamped (model + manifest version + decision boundary)
    assert run.replay.model_version.startswith("google/gemini-2.5-flash-lite")
    assert run.replay.decision_ts == fx.decision_ts
    assert run.replay.config_version == man.manifest_version
