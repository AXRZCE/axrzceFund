"""WP5 R1/R6c red tests — PMORT-01 family discipline, grounding, pending queue. Zero LLM
(a fake client double supplies canned transport; the CHECKS under test are pure code).

Gut map: gut the call-site disjointness loop in resolve_pmort_seat → forced same-family passes →
red; gut check_pmort_grounding → a canned post-mortem passes → red; drop the LLMError handler →
the pending queue never fills → red.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from core.episodic import KnowableAtDecisionTs, Outcome, PostMortem, pending_post_mortems
from core.event_log import EventLog
from core.heterogeneity import HeterogeneityError
from core.llm import LLMError
from core.manifest import load_manifest
from graphs.pmort import PMORTError, check_pmort_grounding, resolve_pmort_seat, run_pmort

MAN = load_manifest()
RECORD = {"proposal": {"ticker": "MDT", "direction": "long", "size_pct_nav": 0.735,
                       "thesis": "sequential revenue growth and margin expansion justify entry",
                       "expected_edge_bps": 400},
          "ballot_summary": {"weighted_score": 1.3, "margin": 0.354167,
                             "dissent_summary": "BEAR-01 voted short (conviction 0.62)"}}


# ── R1: family resolved at call time, disjoint from the DECIDED family ─────────────
def test_pmort_seat_disjoint_from_decided_google():
    spec = resolve_pmort_seat("google", MAN)
    assert spec.family in {"openai", "chinese"} and spec.tier == "T3"


def test_forced_same_family_raises_at_call_site():
    """R1 red test: force family(PMORT) == the decided family while a disjoint one exists."""
    with pytest.raises(HeterogeneityError, match="required where an alternative exists"):
        resolve_pmort_seat("google", MAN, override="google")


def test_resolution_deterministic():
    assert resolve_pmort_seat("google", MAN).role == resolve_pmort_seat("google", MAN).role


# ── R1: grounding — a canned post-mortem citing nothing from the record fails ───────
def _pm(citations):
    return PostMortem(
        trade_id="t", ticker="MDT", outcome_vs_thesis="confirmed",
        luck_skill_assessment="x", premortem_hit=False, process_grade=3, outcome_grade=2,
        knowable_at_decision_ts=KnowableAtDecisionTs(answer=True, citations=citations),
        observable_that_would_have_changed="pre-decision channel checks",
        interim=True, window_days=4)


def test_grounded_citation_passes():
    check_pmort_grounding(_pm(["sequential revenue growth and margin expansion"]), RECORD)


def test_canned_citation_fails():
    with pytest.raises(PMORTError, match="canned"):
        check_pmort_grounding(_pm(["the fortress balance sheet narrative from the roadshow"]), RECORD)


# ── R6c: LLM unavailable ⇒ QUEUED (never skipped, never fabricated) ─────────────────
@dataclass
class _Usage:
    cost_usd: float = 0.0


class _DownClient:
    def call(self, **_):
        raise LLMError("model unavailable (injected)")


class _GoodClient:
    """Test double: transport that returns a valid, RECORD-grounded post-mortem JSON."""

    def call(self, **_):
        class R:
            finish_reason = "stop"
            model_version = "fake/model"
            usage = _Usage(0.0)
            text = json.dumps({
                "outcome_vs_thesis": "confirmed",
                "luck_skill_assessment": "early window, beta-driven",
                "premortem_hit": False, "process_grade": 3, "outcome_grade": 2,
                "knowable_at_decision_ts": {
                    "answer": True,
                    "citations": ["sequential revenue growth and margin expansion justify entry"]},
                "observable_that_would_have_changed": "a guide-down before the decision",
                "lesson": None, "agent_grades": {}})
        return R()


def _run(client, el):
    return run_pmort(trade_id="trade_mdt", ticker="MDT", sector="health", direction="long",
                     decision_record=RECORD,
                     outcome=Outcome(pnl_bps=12.0, holding_days=4, exit_reason="interim_mark"),
                     premortem_top_risks=["hyperscaler capex plateau"],
                     decision_record_ref="results/wp3_cp3/pm_smoke.json",
                     interim=True, window_days=4, decided_family="google",
                     client=client, manifest=MAN, cycle_id="c1",
                     decision_ts="2026-07-02T20:00:00+00:00", code_version="t", event_log=el)


def test_llm_down_queues_pending_never_fabricates(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    r = _run(_DownClient(), el)
    assert r.status == "pending" and r.post_mortem is None
    assert [p["trade_id"] for p in pending_post_mortems(el)] == ["trade_mdt"]
    assert not [e for e in el.get_events(agent_id="PMORT-01") if e.event_type == "post_mortem"]


def test_drain_captures_when_model_returns(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    _run(_DownClient(), el)                            # queue it
    from graphs.pmort import drain_pending
    drained = drain_pending(event_log=el, retry_fn=lambda p: _run(_GoodClient(), el))
    assert drained == ["trade_mdt"]
    assert pending_post_mortems(el) == []
    captured = [e for e in el.get_events(agent_id="PMORT-01") if e.event_type == "post_mortem"]
    assert captured and captured[0].payload["post_mortem"]["interim"] is True


def test_good_client_end_to_end_capture(tmp_path):
    el = EventLog(tmp_path / "ev.db")
    r = _run(_GoodClient(), el)
    assert r.status == "captured"
    assert r.stamp["manifest_version"] == MAN.manifest_version
    assert r.post_mortem.process_grade == 3 and r.post_mortem.outcome_grade == 2
