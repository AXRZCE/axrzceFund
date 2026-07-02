"""WP3 R5 (CP0) — manifest_version is a first-class part of the replay identity.

Anti-hoax: a decision replayed under a DIFFERENT deploy-manifest hash must produce a DIFFERENT
replay identity, so a model/roster swap (e.g. filling the BULL seat with the Chinese open-weight
model) is captured. Gut the stamping — drop `manifest_version` from `ReplayTuple.to_dict()` or
hardcode it to a constant — and `test_manifest_swap_changes_replay_identity` /
`test_manifest_version_in_replay_identity` go RED.

Pure unit: builds tiny manifests on tmp files; no key, no network, no spend.
"""

from __future__ import annotations

from pathlib import Path

from core.manifest import load_manifest
from core.replay import ReplayTuple, new_replay_tuple

_MANIFEST_TMPL = """\
access: openrouter
roles:
  BULL-01:
    family: chinese
    tier: T2
    model_version: {model}
    cutoff: 2026-05-01
    provider:
      only: [fireworks]
      allow_fallbacks: false
"""


def _write_manifest(path: Path, model: str) -> Path:
    path.write_text(_MANIFEST_TMPL.format(model=model), encoding="utf-8")
    return path


def _tuple_with(manifest_version: str) -> ReplayTuple:
    """A fixed 'decision' — everything identical except the manifest hash under test."""
    return ReplayTuple(
        trade_id="trade_fixed", cycle_id="cycle_20260701_0001", decision_ts="2026-06-15T20:00:00+00:00",
        agent_id="BULL-01", prompt_version="v1", model_version="deepseek/v4-pro",
        manifest_version=manifest_version, config_version="cfg_fixed", code_version="code_fixed",
    )


def test_manifest_version_in_replay_identity():
    """manifest_version must be part of the serialized replay identity (drop it -> red)."""
    d = new_replay_tuple(
        cycle_id="c", agent_id="BULL-01", prompt_version="v1", model_version="m",
        manifest_version="mani_abc", config_version="cfg", code_version="code",
    ).to_dict()
    assert d["manifest_version"] == "mani_abc"
    assert d["config_version"] == "cfg"  # distinct field, not the same value


def test_manifest_swap_changes_replay_identity(tmp_path):
    """Same decision, two manifests differing only in the BULL model pin -> different manifest
    hash -> different replay identity. This is the R5 property a Chinese-seat swap must satisfy."""
    m1 = load_manifest(_write_manifest(tmp_path / "m1.yaml", "deepseek/v4-pro"))
    m2 = load_manifest(_write_manifest(tmp_path / "m2.yaml", "zhipu/glm-5.2"))
    assert m1.manifest_version != m2.manifest_version, "different manifests must hash differently"

    rt1 = _tuple_with(m1.manifest_version)
    rt2 = _tuple_with(m2.manifest_version)
    # The ONLY difference is the manifest hash — yet the replay identities must diverge.
    assert rt1.to_dict() != rt2.to_dict()
    assert rt1.to_dict()["manifest_version"] != rt2.to_dict()["manifest_version"]
    # everything else identical (proves the divergence is attributable to the manifest swap)
    d1, d2 = rt1.to_dict(), rt2.to_dict()
    assert {k: v for k, v in d1.items() if k != "manifest_version"} == \
           {k: v for k, v in d2.items() if k != "manifest_version"}


def test_same_manifest_same_identity(tmp_path):
    """Control: the SAME manifest loaded twice yields the same hash -> same replay identity
    (a faithful same-manifest replay must still match)."""
    p = _write_manifest(tmp_path / "m.yaml", "deepseek/v4-pro")
    a = load_manifest(p).manifest_version
    b = load_manifest(p).manifest_version
    assert a == b
    assert _tuple_with(a).to_dict() == _tuple_with(b).to_dict()
