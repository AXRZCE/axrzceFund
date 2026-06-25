"""Fixture harness + R1 post-cutoff gate tests (WP2 — the hardest-to-fake proof).

Anti-hoax: if `load_fixture` were gutted to `return fx` (no gate), the pre-cutoff rejection
tests below go red. The gate keys on the fixture's information-boundary date (decision_ts),
NOT its record date — proven by recording a fixture "today" with a pre-cutoff decision_ts and
still seeing it rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.manifest import load_manifest
from data.fixtures.harness import Fixture, FixtureGateError, load_fixture, record_fixture
from data.pit_store import PITStore

# Binding cutoff for FUND-TECH (Sonnet) is 2026-01-31 in the real manifest.
PRE_CUTOFF_TS = "2026-01-15T21:00:00+00:00"   # at/before the cutoff -> must be rejected
ON_CUTOFF_TS = "2026-01-31T21:00:00+00:00"    # boundary day itself -> still rejected (<=)
POST_CUTOFF_TS = "2026-03-02T21:00:00+00:00"  # strictly after -> allowed


def _store_with_bars(tmp_path: Path, available_at: str) -> PITStore:
    store = PITStore(tmp_path / "pit.duckdb")
    store.insert_price_bars([
        {"ticker": "AAPL", "as_of": available_at, "available_at": available_at,
         "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1000, "source": "sep"},
    ])
    return store


def _record(store: PITStore, tmp_path: Path, fid: str, decision_ts: str) -> Path:
    record_fixture(store, fid, decision_ts, ["AAPL"], out_dir=tmp_path / "fx")
    return tmp_path / "fx" / f"{fid}.json"


def test_pre_cutoff_fixture_is_rejected(tmp_path):
    store = _store_with_bars(tmp_path, "2026-01-10T21:00:00+00:00")
    path = _record(store, tmp_path, "pre", PRE_CUTOFF_TS)
    m = load_manifest()
    with pytest.raises(FixtureGateError, match="R1 reject"):
        load_fixture(path, for_roles=["FUND-TECH"], manifest=m)
    store.close()


def test_on_cutoff_boundary_is_rejected(tmp_path):
    store = _store_with_bars(tmp_path, "2026-01-20T21:00:00+00:00")
    path = _record(store, tmp_path, "boundary", ON_CUTOFF_TS)
    m = load_manifest()
    with pytest.raises(FixtureGateError):
        load_fixture(path, for_roles=["FUND-TECH"], manifest=m)
    store.close()


def test_post_cutoff_fixture_passes(tmp_path):
    store = _store_with_bars(tmp_path, "2026-02-20T21:00:00+00:00")
    path = _record(store, tmp_path, "post", POST_CUTOFF_TS)
    m = load_manifest()
    fx = load_fixture(path, for_roles=["FUND-TECH"], manifest=m)
    assert fx.fixture_id == "post"
    assert fx.tickers == ["AAPL"]
    assert len(fx.payload["price_bars"]) == 1
    store.close()


def test_gate_keys_on_decision_ts_not_record_date(tmp_path):
    """A fixture recorded NOW (recorded_at ~ today, well past the cutoff) but carrying a
    pre-cutoff decision_ts must STILL be rejected — the gate is the information boundary,
    not when we happened to record it."""
    store = _store_with_bars(tmp_path, "2026-01-10T21:00:00+00:00")
    path = _record(store, tmp_path, "stale", PRE_CUTOFF_TS)
    fx = Fixture.from_dict(__import__("json").loads(path.read_text()))
    assert fx.recorded_at > "2026-02"  # recorded after the cutoff window
    assert fx.decision_ts == PRE_CUTOFF_TS  # but the boundary is pre-cutoff
    with pytest.raises(FixtureGateError):
        load_fixture(path, for_roles=["FUND-TECH"], manifest=load_manifest())
    store.close()


def test_binding_cutoff_is_the_max_across_roles(tmp_path):
    """Haiku alone (Jul 2025) would let a Sep-2025 fixture through, but adding Sonnet
    (Jan 2026) raises the binding cutoff so the same fixture is rejected for the pair."""
    store = _store_with_bars(tmp_path, "2025-09-10T21:00:00+00:00")
    path = _record(store, tmp_path, "sep2025", "2025-09-15T21:00:00+00:00")
    m = load_manifest()
    # Allowed for Haiku-only (after Jul 2025)...
    assert load_fixture(path, for_roles=["TECH-01"], manifest=m).fixture_id == "sep2025"
    # ...but rejected once Sonnet (Jan 2026 cutoff) is in the run.
    with pytest.raises(FixtureGateError):
        load_fixture(path, for_roles=["TECH-01", "FUND-TECH"], manifest=m)
    store.close()


def test_lookahead_audit_clean_by_construction(tmp_path):
    store = _store_with_bars(tmp_path, "2026-02-20T21:00:00+00:00")
    path = _record(store, tmp_path, "clean", POST_CUTOFF_TS)
    fx = load_fixture(path, for_roles=["FUND-TECH"], manifest=load_manifest())
    assert fx.audit_lookahead() == []  # no row available_at > decision_ts
    store.close()


def test_lookahead_audit_catches_a_future_row():
    """The audit must actually bite: a hand-crafted fixture with a row stamped after the
    boundary is flagged (guards against the audit silently passing everything)."""
    fx = Fixture(
        fixture_id="bad", decision_ts="2026-03-02T21:00:00+00:00", tickers=["AAPL"],
        payload={"price_bars": [
            {"ticker": "AAPL", "available_at": "2026-04-01T00:00:00+00:00", "close": 9.9},
        ], "fundamentals": {}},
        content_hash="x", recorded_at="2026-06-24T00:00:00+00:00", source="pit_store",
    )
    bad = fx.audit_lookahead()
    assert len(bad) == 1 and bad[0]["close"] == 9.9
