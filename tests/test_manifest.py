"""Deployment-manifest loader tests (WP2 — R1 source layer)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.manifest import ManifestError, ModelSpec, load_manifest


def test_real_manifest_loads_with_wp2_value_roster():
    m = load_manifest()  # deploy/model_manifest.yaml
    assert m.access == "openrouter"
    assert len(m.manifest_version) == 12
    # WP2 in-scope research pool — value-frontier, NO Anthropic (ADR-2 amendment 2026-06-25)
    assert {"TECH-01", "FUND-TECH", "SENT-01"} <= set(m.specs)
    assert m.resolve("TECH-01").model_version == "google/gemini-2.5-flash-lite"
    assert m.resolve("FUND-TECH").model_version == "google/gemini-3.1-pro-preview"
    assert m.resolve("SENT-01").model_version == "openai/gpt-5.4"
    assert not any("anthropic" in s.model_version for s in m.specs.values())


def test_cp1_comparison_roles_present_western_host_pinned():
    """WP3 CP1: the BULL-seat comparison candidates load, Chinese models are Western-host-pinned,
    and the binding cutoff for the comparison is the MAX across the compared models."""
    m = load_manifest()
    cmp_roles = ["BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM", "BULL-01-BASELINE-WEST"]
    assert set(cmp_roles) <= set(m.specs)
    # Chinese candidates on approved WESTERN hosts (R1)
    assert m.resolve("BULL-01-CAND-DEEPSEEK").family == "chinese"
    assert m.resolve("BULL-01-CAND-DEEPSEEK").provider["only"] == ["fireworks"]
    assert m.resolve("BULL-01-CAND-GLM").provider["only"] == ["together"]
    # binding cutoff for the comparison = MAX(deepseek 2026-04-30, glm 2026-05-15, west 2026-02-19)
    assert m.binding_cutoff(cmp_roles) == date(2026, 5, 15)


def test_cp1_judge_family_disjoint_from_every_compared_model():
    """R6 in miniature: the CP1 scoring judge must be a family disjoint from EVERY judged model."""
    from core.heterogeneity import assert_judge_disjoint

    m = load_manifest()
    judge_family = m.resolve("VERIF-CP1-JUDGE").family  # openai
    judged = [m.resolve(r).family for r in
              ("BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM", "BULL-01-BASELINE-WEST")]
    available = {s.family for s in m.specs.values()}
    for jf in judged:
        assert_judge_disjoint(judge_family, jf, available)  # must NOT raise (openai != chinese/google)


def test_western_host_pin_red_a_chinese_model_on_a_non_western_host_fails(tmp_path: Path):
    """R1 red test: a Chinese-origin (family: chinese) model pinned to a NON-Western host
    (e.g. the first-party `deepseek` API) must FAIL to load — gut the WESTERN_HOSTS check → green."""
    bad = tmp_path / "leak.yaml"
    bad.write_text(
        "roles:\n"
        "  BULL-01-CAND-DEEPSEEK:\n"
        "    family: chinese\n"
        "    tier: T2\n"
        "    model_version: deepseek/deepseek-v4-pro\n"
        "    cutoff: 2026-04-30\n"
        "    provider:\n"
        "      only: [deepseek]\n"          # non-Western first-party host -> data egress risk
        "      allow_fallbacks: false\n"
    )
    with pytest.raises(ManifestError, match="WESTERN inference host"):
        load_manifest(bad)


def test_western_host_pin_allows_chinese_model_on_western_host(tmp_path: Path):
    """Control: the SAME Chinese model on an approved Western host (Fireworks) loads fine."""
    ok = tmp_path / "ok.yaml"
    ok.write_text(
        "roles:\n"
        "  BULL-01-CAND-DEEPSEEK:\n"
        "    family: chinese\n"
        "    tier: T2\n"
        "    model_version: deepseek/deepseek-v4-pro\n"
        "    cutoff: 2026-04-30\n"
        "    provider:\n"
        "      only: [fireworks]\n"
        "      allow_fallbacks: false\n"
    )
    m = load_manifest(ok)
    assert m.resolve("BULL-01-CAND-DEEPSEEK").provider["only"] == ["fireworks"]


def test_binding_cutoff_is_max_availability_cutoff():
    m = load_manifest()
    # Availability-date cutoffs: gemini-flash-lite 2025-07-22, gemini-3.1-pro 2026-02-19,
    # gpt-5.4 2026-03-05 -> the max binds.
    assert m.binding_cutoff(["TECH-01"]) == date(2025, 7, 22)
    assert m.binding_cutoff(["FUND-TECH"]) == date(2026, 2, 19)
    assert m.binding_cutoff(["TECH-01", "FUND-TECH", "SENT-01"]) == date(2026, 3, 5)


def test_unknown_role_raises():
    m = load_manifest()
    with pytest.raises(ManifestError):
        m.resolve("MACRO-01")
    with pytest.raises(ManifestError):
        m.binding_cutoff([])


def test_fail_closed_on_missing_cutoff(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "access: openrouter\n"
        "roles:\n"
        "  TECH-01:\n"
        "    family: anthropic\n"
        "    tier: T1.5\n"
        "    model_version: anthropic/claude-haiku-4.5\n"  # cutoff deliberately absent
    )
    with pytest.raises(ManifestError, match="cutoff"):
        load_manifest(bad)


def test_fail_closed_on_unparseable_cutoff(tmp_path: Path):
    bad = tmp_path / "bad2.yaml"
    bad.write_text(
        "roles:\n"
        "  TECH-01:\n"
        "    family: anthropic\n"
        "    tier: T1.5\n"
        "    model_version: anthropic/claude-haiku-4.5\n"
        "    cutoff: 'July 2025'\n"  # not ISO
        "    provider:\n"
        "      only: [anthropic]\n"
    )
    with pytest.raises(ManifestError, match="ISO date"):
        load_manifest(bad)


def test_provider_pin_present_and_loaded():
    """Replay completeness: every role must pin its OpenRouter backend so model_version
    alone doesn't under-specify what ran (OpenRouter load-balances slugs across backends).
    All WP2 backends are Western-hosted."""
    m = load_manifest()
    expected = {
        "TECH-01": ["google-vertex"],
        "FUND-TECH": ["google-vertex"],
        "SENT-01": ["openai"],
    }
    for role, only in expected.items():
        prov = m.resolve(role).provider
        assert prov.get("only") == only
        assert prov.get("allow_fallbacks") is False


def test_fail_closed_on_missing_provider(tmp_path: Path):
    bad = tmp_path / "noprov.yaml"
    bad.write_text(
        "roles:\n"
        "  FUND-TECH:\n"
        "    family: anthropic\n"
        "    tier: T2\n"
        "    model_version: anthropic/claude-sonnet-4.6\n"
        "    cutoff: 2026-01-31\n"  # provider deliberately absent
    )
    with pytest.raises(ManifestError, match="provider"):
        load_manifest(bad)


def test_fail_closed_on_unpinned_provider(tmp_path: Path):
    """A provider block with neither `only` nor `order` is not a pin -> rejected."""
    bad = tmp_path / "looseprov.yaml"
    bad.write_text(
        "roles:\n"
        "  FUND-TECH:\n"
        "    family: anthropic\n"
        "    tier: T2\n"
        "    model_version: anthropic/claude-sonnet-4.6\n"
        "    cutoff: 2026-01-31\n"
        "    provider:\n"
        "      allow_fallbacks: true\n"  # present but doesn't pin a backend
    )
    with pytest.raises(ManifestError, match="provider"):
        load_manifest(bad)


def test_modelspec_cutoff_date_parses():
    spec = ModelSpec(role="X", family="anthropic", tier="T2",
                     model_version="anthropic/claude-sonnet-4.6", cutoff="2026-01-31",
                     provider={"only": ["anthropic"], "allow_fallbacks": False})
    assert spec.cutoff_date == date(2026, 1, 31)
