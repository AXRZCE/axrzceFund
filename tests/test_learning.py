"""WP5 R2/R3/R4 red tests — schemas, capture, rebuild, retrieval, isolation. Pure code, zero LLM.

THE BOUNDARY TEST IS FIRST (the gate's ordering rule): no weight/believability field may exist in
any WP5 schema — believability weighting is Phase 3 (memory-systems §5.2: no write API exists).
Gut map: add a `weight` field → the scan red; break rebuild determinism → byte-equal red; import
episodic into a live module → isolation scan red; add an update/delete surface → append-only red.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import core.episodic as episodic
from core.episodic import (
    Episode,
    KnowableAtDecisionTs,
    LessonCandidate,
    Outcome,
    PostMortem,
    capture_pmort_pending,
    capture_post_mortem,
    pending_post_mortems,
    rebuild_episodic_store,
    retrieve,
)
from core.event_log import EventLog
from core.manifest import load_manifest

FORBIDDEN_FIELD_PAT = re.compile(r"weight|believab|w_i\b|multiplier", re.IGNORECASE)
WP5_SCHEMAS = (LessonCandidate, KnowableAtDecisionTs, PostMortem, Outcome, Episode)


# ── R3 THE PHASE-3 BOUNDARY — first, before anything it bounds ─────────────────────
def test_no_weight_or_believability_field_in_any_wp5_schema():
    """R3 red test: a weights/believability field appearing ANYWHERE in the WP5 schemas = red.
    (extra='forbid' blocks smuggling at runtime; this scan blocks it at the source.)"""
    offending = []
    for model in WP5_SCHEMAS:
        for name in model.model_fields:
            if FORBIDDEN_FIELD_PAT.search(name):
                offending.append(f"{model.__name__}.{name}")
    assert not offending, f"Phase-3 boundary breached — weight-like fields: {offending}"


def test_schemas_reject_smuggled_weight_at_runtime():
    with pytest.raises(ValidationError):
        LessonCandidate(text="t", generalizable=False, tags=[], weight=0.7)  # type: ignore[call-arg]


def test_no_write_api_for_believability_exists():
    """memory-systems §5.2: 'No write API exists.' Honored by not building one — no function in
    core/episodic mentions believability."""
    src = Path("core/episodic.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert not [f for f in fn_names if FORBIDDEN_FIELD_PAT.search(f)]


# ── R2: the §6.3 taxonomy, schema-enforced ─────────────────────────────────────────
def _pm(**over):
    base = dict(
        trade_id="trade_x", ticker="MDT", outcome_vs_thesis="confirmed",
        luck_skill_assessment="early confirmation, mostly market beta so far",
        premortem_hit=False, process_grade=3, outcome_grade=2,
        knowable_at_decision_ts=KnowableAtDecisionTs(
            answer=True, citations=["sequential revenue growth cited at decision time"]),
        observable_that_would_have_changed="a guide-down in the pre-decision channel checks",
        lesson=None, agent_grades={}, interim=True, window_days=4)
    base.update(over)
    return PostMortem(**base)


def test_process_and_outcome_are_separate_required_fields():
    pm = _pm(process_grade=1, outcome_grade=4)  # a win with a flawed process — representable
    assert pm.process_grade != pm.outcome_grade


def test_out_of_enum_verdict_rejected():
    with pytest.raises(ValidationError):
        _pm(outcome_vs_thesis="sorta_right")


def test_knowable_requires_citations():
    with pytest.raises(ValidationError):
        _pm(knowable_at_decision_ts=KnowableAtDecisionTs(answer=True, citations=[]))


def test_empty_observable_rejected_as_unfinished():
    with pytest.raises(ValidationError, match="unfinished"):
        _pm(observable_that_would_have_changed="   ")


def test_interim_forbids_generalizable_lessons():
    """R6b: no promotion off partial windows."""
    with pytest.raises(ValidationError, match="anecdote"):
        _pm(lesson=LessonCandidate(text="always fade AI capex", generalizable=True, tags=["ai"]))
    ok = _pm(lesson=LessonCandidate(text="note only", generalizable=False, tags=[]))
    assert ok.lesson is not None


def test_interim_requires_window_days():
    with pytest.raises(ValidationError, match="window_days"):
        _pm(window_days=None)


def test_lesson_capped_at_50_words():
    with pytest.raises(ValidationError, match="50 words"):
        LessonCandidate(text=" ".join(["word"] * 51), generalizable=False, tags=[])


# ── R3: append-only capture, replay-stamped, byte-equal rebuild ────────────────────
def _episode(trade_id="trade_x"):
    return Episode(trade_id=trade_id, cycle_id="cycle_20260702_0001", ticker="MDT",
                   sector="health", direction="long", tags=["interim"],
                   decision_record_ref="results/wp3_cp3/pm_smoke.json",
                   outcome=Outcome(pnl_bps=12.0, holding_days=4, exit_reason="interim_mark"),
                   premortem_hit=False, post_mortem_ref="event:post_mortem:trade_x",
                   interim=True, window_days=4)


def test_capture_stamps_manifest_version_and_probation_status(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    man = load_manifest()
    pm = _pm(interim=False, window_days=None,
             lesson=LessonCandidate(text="a closed-window lesson", generalizable=True, tags=["x"]))
    stamp = capture_post_mortem(event_log=el, post_mortem=pm, episode=_episode(), manifest=man,
                                cycle_id="c1", decision_ts="2026-07-02T20:00:00+00:00",
                                code_version="t", agent_model_version="m")
    assert stamp["manifest_version"] == man.manifest_version
    events = el.get_events(agent_id="PMORT-01")
    types = [e.event_type for e in events]
    assert "post_mortem" in types and "lesson_candidate" in types
    lesson_evt = [e for e in events if e.event_type == "lesson_candidate"][0]
    assert lesson_evt.payload["status"] == "probation"  # memory-systems §4.2 step 1


def test_records_are_immutable_append_only():
    ep = _episode()
    with pytest.raises(ValidationError):
        ep.ticker = "AVGO"  # frozen model — no mutation surface (R3)
    src = Path("core/episodic.py").read_text(encoding="utf-8")
    assert "def update_" not in src and "def delete_" not in src


def test_rebuild_is_byte_equal_and_recovers_corruption(tmp_path):
    """R3 red test: the derived store is a VIEW — corrupt it, rebuild, byte-equal restored."""
    el = EventLog(tmp_path / "ev.db")
    man = load_manifest()
    for tid in ("trade_b", "trade_a"):
        capture_post_mortem(event_log=el, post_mortem=_pm(trade_id=tid), episode=_episode(tid),
                            manifest=man, cycle_id="c1",
                            decision_ts="2026-07-02T20:00:00+00:00",
                            code_version="t", agent_model_version="m")
    p = tmp_path / "store.json"
    first = rebuild_episodic_store(el, p)
    p.write_bytes(b'{"episodes": "CORRUPTED"}')
    second = rebuild_episodic_store(el, p)
    assert first == second == p.read_bytes()          # byte-equal, deterministic
    eps = json.loads(first)["episodes"]
    assert [e["trade_id"] for e in eps] == ["trade_a", "trade_b"]  # sorted, not insertion order


# ── R6c: the pending queue is derived from the log (survives restart) ──────────────
def test_pending_queue_from_log_and_clears_on_capture(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    man = load_manifest()
    capture_pmort_pending(event_log=el, trade_id="trade_q", cycle_id="c1", reason="LLM down")
    assert [p["trade_id"] for p in pending_post_mortems(el)] == ["trade_q"]
    el2 = EventLog(tmp_path / "ev.db")                 # "restart": re-open the log
    assert [p["trade_id"] for p in pending_post_mortems(el2)] == ["trade_q"]
    capture_post_mortem(event_log=el2, post_mortem=_pm(trade_id="trade_q"),
                        episode=_episode("trade_q"), manifest=man, cycle_id="c1",
                        decision_ts="2026-07-02T20:00:00+00:00",
                        code_version="t", agent_model_version="m")
    assert pending_post_mortems(el2) == []             # captured ⇒ no longer pending


# ── R4: retrieval works; the live path is structurally isolated ────────────────────
def test_retrieval_by_ticker_direction_tags_dates():
    eps = [_episode("trade_a").model_dump(),
           {**_episode("trade_b").model_dump(), "ticker": "COST", "direction": "no_trade",
            "tags": ["no_trade"], "cycle_id": "cycle_20260630_0001"}]
    assert [e["trade_id"] for e in retrieve(eps, ticker="MDT")] == ["trade_a"]
    assert [e["trade_id"] for e in retrieve(eps, direction="no_trade")] == ["trade_b"]
    assert [e["trade_id"] for e in retrieve(eps, tags=["no_trade"])] == ["trade_b"]
    assert [e["trade_id"] for e in retrieve(eps, date_to="cycle_20260701")] == ["trade_b"]
    assert retrieve(eps, ticker="ZZZZ") == []          # distinct queries ⇒ distinct results


LIVE_PATH_MODULES = ["graphs/deep_loop.py", "graphs/debate.py", "graphs/ballot.py",
                     "graphs/pm.py", "graphs/risk_gate.py", "graphs/orders.py",
                     "graphs/monitor.py", "graphs/judge.py"]


def _imports_of(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        if isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    return mods


def test_isolation_no_live_module_reads_the_memory_store():
    """R4 red test (the shadow pattern): NOTHING reads lessons into live decisions in Phase 1.
    Add `import core.episodic` to any live-path module (the gut) → red."""
    offending = {m for m in LIVE_PATH_MODULES
                 if any(i.startswith(("core.episodic", "graphs.pmort")) for i in _imports_of(m))}
    assert not offending, f"live-path modules read the memory store: {offending}"


def test_isolation_memory_store_reads_no_live_state():
    """And the store itself imports neither CycleState's module nor the deep loop."""
    for m in ("core/episodic.py",):
        bad = [i for i in _imports_of(m) if i.startswith(("graphs.state", "graphs.deep_loop"))]
        assert not bad, f"{m} imports live state: {bad}"
