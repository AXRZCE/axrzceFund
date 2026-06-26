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
    assert set(m.specs) == {"TECH-01", "FUND-TECH", "SENT-01"}
    assert m.resolve("TECH-01").model_version == "google/gemini-2.5-flash-lite"
    assert m.resolve("FUND-TECH").model_version == "google/gemini-3.1-pro-preview"
    assert m.resolve("SENT-01").model_version == "openai/gpt-5.4"
    assert not any("anthropic" in s.model_version for s in m.specs.values())


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
