"""WP5 R5 red tests — the dashboard renders REAL committed records, or fails.

Gut map: add a sample-data fallback → the missing-artifact test red + the source scan red;
render a hardcoded number → the spot-value tests (values read FROM the artifacts at test time,
never constants) red.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ops.build_dashboard import ARTIFACTS, load_artifacts, render

REPO = Path(".")


def _html() -> str:
    return render(load_artifacts())


def test_missing_artifact_fails_the_build(tmp_path, monkeypatch):
    """R5 red test: no placeholder render, ever — a missing record breaks the build."""
    import ops.build_dashboard as dash
    broken = dict(ARTIFACTS)
    broken["wp4_replay"] = tmp_path / "nope.json"
    monkeypatch.setattr(dash, "ARTIFACTS", broken)
    with pytest.raises(FileNotFoundError, match="fails the build"):
        dash.load_artifacts()


def test_spot_values_equal_artifact_values():
    """≥5 spot values across WPs, read FROM the artifacts at test time (incl. one cost_bps and
    the ballot margin) — rendered numbers must be the artifact numbers."""
    html = _html()
    seat = json.loads(ARTIFACTS["wp3_seat"].read_text())
    full = json.loads(ARTIFACTS["wp3_full"].read_text())
    pm = json.loads(ARTIFACTS["wp3_pm"].read_text())
    wp4 = json.loads(ARTIFACTS["wp4_replay"].read_text())
    wp5 = json.loads(ARTIFACTS["wp5_pmort"].read_text())

    spots = [
        str(seat["per_model"]["BULL-01-CAND-GLM"]["mean_composite"]),      # 1. the seated mean
        str(full["ballot"]["summary"]["margin"]),                          # 2. the ballot margin
        str(wp4["cases"][0]["cost_bps"]),                                  # 3. a per-trade cost
        str(pm["pm_decision"]["proposal"]["size_pct_nav"]),                # 4. the MDT size
        wp4["halt_end_to_end_demo"]["regated_proposal"]["rule"],           # 5. the halt rule
        str(wp5["mdt_interim"]["outcome"]["pnl_bps"]),                     # 6. the interim pnl
        str(wp5["spend"]["cumulative_ledger_usd"]),                        # 7. the ledger total
    ]
    missing = [s for s in spots if s not in html]
    assert not missing, f"rendered dashboard is missing artifact values: {missing}"


def test_contested_flag_renders_from_artifact():
    """The CP4 organic contested ballot must show as CONTESTED (read from the artifact)."""
    full = json.loads(ARTIFACTS["wp3_full"].read_text())
    assert full["ballot"]["summary"]["contested"] is True
    assert "CONTESTED" in _html()


def test_no_sample_data_in_generator():
    src = Path("ops/build_dashboard.py").read_text(encoding="utf-8")
    for banned in ("sample_data", "SAMPLE", "lorem", "placeholder_", "fake_"):
        assert banned not in src, f"sample-data path found in the generator: {banned}"


def test_committed_output_matches_regeneration(tmp_path):
    """The committed results/dashboard/index.html must equal a fresh regeneration (no drift)."""
    committed = Path("results/dashboard/index.html")
    if not committed.exists():
        pytest.skip("dashboard output not built yet (built at CP2 before commit)")
    assert committed.read_text(encoding="utf-8") == _html()
