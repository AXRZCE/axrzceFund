"""VERIF-01 deterministic validator tests (WP2, R3).

Anti-hoax: every bad-memo case asserts `valid is False`; gutting `verify_memo` to
`return VerificationResult(True, [], [])` turns them all red.
"""

from __future__ import annotations

import copy

from graphs.verif01 import verify_memo


def _clean_tech_memo() -> dict:
    return {
        "agent_id": "TECH-01",
        "ticker": "AAPL",
        "stance": "long",
        "conviction": 0.6,
        "horizon_days": 20,
        "thesis": "Uptrend intact above the 50-day; a pullback to support is a buyable level.",
        "key_claims": [
            {"claim": "price above 50-day MA", "evidence": ["bar_2026_06"], "claim_type": "fact"},
            {"claim": "volume confirms the move", "evidence": ["bar_2026_06"], "claim_type": "fact"},
            {"claim": "momentum positive", "evidence": [], "claim_type": "inference"},
        ],
        "catalysts": [],
        "invalidation_conditions": ["close below 50-day MA"],
        "risks": ["market-wide drawdown"],
        "what_would_change_my_mind": "A decisive close below the 50-day on heavy volume.",
        "technical_block": {
            "trend": "up",
            "key_levels": [180.0, 195.0],
            "adv_pct_at_proposed_size": 0.4,
            "abnormal_volume": False,
        },
    }


def _clean_fund_memo() -> dict:
    return {
        "agent_id": "FUND-TECH", "ticker": "AAPL", "stance": "long", "conviction": 0.5,
        "horizon_days": 60, "thesis": "Reasonable multiple vs peers; FCF supports the level.",
        "key_claims": [
            {"claim": "P/E below 5y median", "evidence": ["sf1_pe"], "claim_type": "fact"},
            {"claim": "FCF growing", "evidence": ["sf1_fcf"], "claim_type": "fact"},
            {"claim": "margin durable", "evidence": [], "claim_type": "estimate"},
        ],
        "catalysts": [], "invalidation_conditions": ["guidance cut"], "risks": ["demand softness"],
        "what_would_change_my_mind": "A structural margin decline in the next print.",
        "valuation_block": {"method": "multiples", "fair_value_range": [180.0, 220.0],
                            "key_assumptions": ["8% rev growth", "stable margins"]},
    }


# ── clean memos pass ─────────────────────────────────────────────────────────────
def test_clean_tech_memo_passes():
    r = verify_memo(_clean_tech_memo(), agent_role="TECH-01")
    assert r.valid and r.schema_violations == [] and r.stripped_claims == []


def test_clean_fund_memo_passes():
    assert verify_memo(_clean_fund_memo(), agent_role="FUND-TECH").valid


# ── constructed bad memos are rejected (valid is False) ──────────────────────────
def test_out_of_range_conviction_rejected():
    m = _clean_tech_memo(); m["conviction"] = 1.5
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("conviction" in v for v in r.schema_violations)


def test_missing_what_would_change_my_mind_rejected():
    m = _clean_tech_memo(); del m["what_would_change_my_mind"]
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("what_would_change_my_mind" in v for v in r.schema_violations)


def test_stray_field_rejected():
    m = _clean_tech_memo(); m["price_target"] = 250.0  # not in the schema
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("price_target" in v for v in r.schema_violations)


def test_missing_block_rejected():
    m = _clean_tech_memo(); del m["technical_block"]
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("technical_block" in v for v in r.schema_violations)


def test_missing_valuation_block_rejected():
    m = _clean_fund_memo(); del m["valuation_block"]
    r = verify_memo(m, agent_role="FUND-TECH")
    assert not r.valid and any("valuation_block" in v for v in r.schema_violations)


def test_too_few_key_claims_rejected():
    m = _clean_tech_memo(); m["key_claims"] = m["key_claims"][:2]
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("key_claims" in v for v in r.schema_violations)


def test_too_many_key_claims_rejected():
    m = _clean_tech_memo()
    m["key_claims"] = [copy.deepcopy(m["key_claims"][0]) for _ in range(8)]
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("key_claims" in v for v in r.schema_violations)


def test_thesis_too_long_rejected():
    m = _clean_tech_memo(); m["thesis"] = "word " * 151
    r = verify_memo(m, agent_role="TECH-01")
    assert not r.valid and any("thesis" in v for v in r.schema_violations)


def test_unknown_role_rejected():
    assert not verify_memo(_clean_tech_memo(), agent_role="MACRO-01").valid


# ── uncited fact claim is STRIPPED, not rejected ─────────────────────────────────
def test_uncited_fact_claim_is_stripped_not_rejected():
    m = _clean_tech_memo()
    m["key_claims"][0]["evidence"] = []  # a `fact` claim with no doc_id
    r = verify_memo(m, agent_role="TECH-01")
    assert r.valid                       # schema/cardinality fine -> still valid
    assert len(r.stripped_claims) == 1   # but the uncited fact is flagged for stripping
    # an inference claim with no evidence is NOT stripped (only `fact` needs a cite)
    assert all("momentum" not in s["claim"] for s in r.stripped_claims)
