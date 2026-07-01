"""Commit-blocker tests (WP2 leak fix). Proves the guard fires on vendor data (any source) and
lets our own outputs through. Anti-hoax: gut `is_vendor_data` to always-None and the block
assertions go red."""

from __future__ import annotations

import json

from ops.precommit_guard import is_vendor_data

# a Sharadar-shaped fixture (as recorded by data/fixtures/harness.py)
_FIXTURE = json.dumps({
    "fixture_id": "x", "decision_ts": "2026-06-24T20:00:00+00:00", "tickers": ["BNC"],
    "payload": {
        "price_bars": [{"ticker": "BNC", "as_of": "2026-06-24", "close": 1.2, "volume": 10}],
        "fundamentals": {"REVENUE": [{"ticker": "BNC", "indicator": "REVENUE", "value": 7.3e6}]},
    },
    "content_hash": "abc", "recorded_at": "2026-06-25T00:00:00+00:00", "source": "pit_store",
}).encode()


# ── blocked: vendor data, any source / any location ──────────────────────────────
def test_blocks_fixture_by_path():
    assert is_vendor_data("data/fixtures/golden/fund_tech_20260624.json", _FIXTURE)
    assert is_vendor_data("data/fixtures/recorded/anything.json", b"{}")


def test_blocks_vendor_schema_outside_fixtures_dir():
    # a leak committed somewhere else still caught by the schema match (price_bars rows)
    alpaca = json.dumps({"price_bars": [{"ticker": "AAPL", "open": 1, "close": 2}]}).encode()
    assert is_vendor_data("data/scratch/iex_dump.json", alpaca)
    benzinga = json.dumps({"news": [{"headline": "x", "ticker": "AAPL"}]}).encode()
    assert is_vendor_data("notes/news.json", benzinga)


def test_blocks_raw_stores_by_extension():
    assert is_vendor_data("data/anything.parquet")
    assert is_vendor_data("var/pit_store.duckdb")


# ── allowed: our code, hash-locks, and our own outputs ───────────────────────────
def test_allows_code_and_locks():
    assert is_vendor_data("data/fixtures/harness.py") is None
    assert is_vendor_data("data/fixtures/__init__.py") is None
    assert is_vendor_data("data/fixtures/locks/fund_tech_20260624.lock.json", b'{"content_hash":"abc"}') is None


def test_allows_our_own_outputs():
    # reports / orders / fills commit normally — no vendor row arrays
    order = json.dumps({"orders": [{"symbol": "AAPL", "qty": 10, "side": "buy"}], "trade_id": "t1"}).encode()
    assert is_vendor_data("results/orders_20260624.json", order) is None
    report = json.dumps({"pnl": 123.4, "positions": [{"symbol": "AAPL", "mv": 100}]}).encode()
    assert is_vendor_data("results/daily_report.json", report) is None
    # a report that merely mentions "fundamentals" as a scalar summary is fine (not a row array)
    summary = json.dumps({"fundamentals": "reviewed", "verdict": "pass"}).encode()
    assert is_vendor_data("docs/note.json", summary) is None


def test_gate_json_result_artifacts_pass():
    # g01-readout / g04-replay style: our computed stats, not vendor rows
    stats = json.dumps({"pbo": 0.51, "dsr_p": 0.03, "seeds": [40, 41, 42]}).encode()
    assert is_vendor_data("docs/g01-readout-final.json", stats) is None
