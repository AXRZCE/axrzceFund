"""WP3 CP1 — the committed hash-lock captures identity + content_hash + payload SIZES only, never
the licensed vendor rows. Anti-hoax for the public-repo data policy: the lock must be committable
without leaking Sharadar values. Pure unit (constructs a Fixture; no pit_store, no network)."""

from __future__ import annotations

import json

from data.fixtures.harness import Fixture, lock_from_fixture, write_lock


def _fx() -> Fixture:
    return Fixture(
        fixture_id="cp1_test_20260626",
        decision_ts="2026-06-26T20:00:00+00:00",
        tickers=["AVGO", "COST"],
        payload={
            "price_bars": [
                {"ticker": "AVGO", "close": 1234.5, "available_at": "2026-06-26T00:00:00+00:00"}
            ],
            "fundamentals": {
                "EPS": [{"ticker": "AVGO", "value": 6.78, "available_at": "2026-06-20T00:00:00+00:00"}],
                "REVENUE": [
                    {"ticker": "AVGO", "value": 9e9, "available_at": "2026-06-20T00:00:00+00:00"},
                    {"ticker": "COST", "value": 6e10, "available_at": "2026-06-20T00:00:00+00:00"},
                ],
            },
        },
        content_hash="abc1230000000000",
        recorded_at="2026-07-01T00:00:00+00:00",
        source="pit_store",
    )


def test_lock_has_identity_hash_and_sizes():
    lk = lock_from_fixture(_fx())
    assert lk["fixture_id"] == "cp1_test_20260626"
    assert lk["content_hash"] == "abc1230000000000"
    assert lk["tickers"] == ["AVGO", "COST"]
    assert lk["payload_summary"] == {"price_bars": 1, "fundamentals": {"EPS": 1, "REVENUE": 2}}


def test_lock_does_not_leak_vendor_rows():
    blob = json.dumps(lock_from_fixture(_fx()))
    # No raw payload, no row-level keys, no licensed numeric values.
    assert "payload" not in json.loads(blob)
    for leak in ("close", "available_at", "\"value\"", "1234.5", "6.78"):
        assert leak not in blob, f"lock leaked vendor detail: {leak!r}"


def test_write_lock_writes_only_the_lock(tmp_path):
    p = write_lock(_fx(), out_dir=tmp_path)
    assert p.name == "cp1_test_20260626.lock.json"
    d = json.loads(p.read_text())
    assert d["content_hash"] == "abc1230000000000" and "payload" not in d
