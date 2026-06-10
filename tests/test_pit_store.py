"""Tests for the PIT store — including the G0.2 look-ahead refusal gate.

G0.2 criteria (validation-criteria.md):
  - A read with available_at > decision_ts is REFUSED by the store
  - AND caught by the nightly audit query
Both conditions must pass independently.
"""

import tempfile
from pathlib import Path

import pytest

from data.pit_store import PITStore, PITViolation


@pytest.fixture
def store():
    """Fresh in-memory-equivalent PIT store for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        s = PITStore(Path(tmpdir) / "pit.duckdb")
        yield s
        s.close()


# ── Helper data ────────────────────────────────────────────────────────────────

def _bar(ticker="AAPL", as_of="2026-01-02T00:00:00+00:00",
         available_at="2026-01-02T21:00:00+00:00", close=150.0, source="iex"):
    return dict(ticker=ticker, as_of=as_of, available_at=available_at,
                pit_grade="ingestion-stamped", open=148.0, high=152.0,
                low=147.0, close=close, volume=10_000_000, source=source)


def _fund(ticker="AAPL", as_of="2025-12-31T00:00:00+00:00",
          available_at="2026-01-15T00:00:00+00:00", value=6.05):
    return dict(ticker=ticker, dimension="ARQ", period="2025Q4",
                as_of=as_of, available_at=available_at,
                pit_grade="native", indicator="EPS", value=value)


# ── Normal read tests ──────────────────────────────────────────────────────────

class TestPITStoreBasic:
    def test_insert_and_read_price_bars(self, store):
        store.insert_price_bars([_bar()])
        bars = store.get_price_bars(["AAPL"], as_known_at="2026-01-03T00:00:00+00:00")
        assert len(bars) == 1
        assert bars[0]["ticker"] == "AAPL"
        assert bars[0]["close"] == 150.0

    def test_read_filters_to_known_bars(self, store):
        """start_date filtering with all data in store having available_at in the past.
        No PITViolation — query returns only bars matching start_date filter."""
        store.insert_price_bars([
            _bar(as_of="2026-01-01T00:00:00+00:00",
                 available_at="2026-01-01T21:00:00+00:00", close=148.0),
            _bar(as_of="2026-01-02T00:00:00+00:00",
                 available_at="2026-01-02T21:00:00+00:00", close=150.0),
        ])
        # Both bars available_at (Jan 1 9pm, Jan 2 9pm) are before as_known_at (Jan 3)
        # so no PITViolation; start_date filter returns only the Jan 2 bar
        bars = store.get_price_bars(
            ["AAPL"],
            as_known_at="2026-01-03T00:00:00+00:00",
            start_date="2026-01-02T00:00:00+00:00",
        )
        assert len(bars) == 1
        assert bars[0]["close"] == 150.0

    def test_insert_and_read_fundamentals(self, store):
        store.insert_fundamentals([_fund()])
        rows = store.get_fundamentals(
            ["AAPL"], "EPS", as_known_at="2026-02-01T00:00:00+00:00"
        )
        assert len(rows) == 1
        assert rows[0]["value"] == 6.05

    def test_insert_and_read_universe(self, store):
        store.insert_universe([
            dict(index_name="SP500", ticker="AAPL",
                 as_of="2026-01-01T00:00:00+00:00",
                 available_at="2026-01-01T21:00:00+00:00",
                 pit_grade="native", in_index=True),
            dict(index_name="SP500", ticker="MSFT",
                 as_of="2026-01-01T00:00:00+00:00",
                 available_at="2026-01-01T21:00:00+00:00",
                 pit_grade="native", in_index=True),
        ])
        universe = store.get_universe("SP500", "2026-01-02T00:00:00+00:00")
        assert "AAPL" in universe
        assert "MSFT" in universe

    def test_staleness_check(self, store):
        store.insert_price_bars([_bar()])
        result = store.staleness_check("price_bars", max_age_hours=26.0)
        # Fresh data from today should be stale (available_at is Jan 2026, far in the past)
        assert result["is_stale"] is True  # Old fixture data is stale by design

    def test_impossible_timestamps_rejected(self, store):
        """available_at < as_of is physically impossible — must be rejected."""
        with pytest.raises(ValueError, match="impossible"):
            store.insert_price_bars([
                _bar(as_of="2026-01-03T00:00:00+00:00",
                     available_at="2026-01-02T00:00:00+00:00")  # available BEFORE event
            ])


# ── G0.2 Look-ahead refusal (the critical gate test) ──────────────────────────

class TestLookAheadRefusal:
    """G0.2: store refuses available_at > decision_ts. Threshold is zero, forever."""

    def test_price_bars_refusal(self, store):
        """G0.2a: get_price_bars raises PITViolation when data is future-available."""
        store.insert_price_bars([
            _bar(available_at="2026-01-05T21:00:00+00:00")  # available Jan 5
        ])
        # Decision ts is Jan 3 — the bar isn't available yet
        with pytest.raises(PITViolation) as exc_info:
            store.get_price_bars(["AAPL"], as_known_at="2026-01-03T00:00:00+00:00")

        err = exc_info.value
        assert "2026-01-03" in err.as_known_at
        assert "look-ahead" in str(err).lower() or "pit violation" in str(err).lower()

    def test_fundamentals_refusal(self, store):
        """G0.2b: get_fundamentals raises PITViolation on future data."""
        store.insert_fundamentals([
            _fund(available_at="2026-03-01T00:00:00+00:00")  # filed March
        ])
        with pytest.raises(PITViolation):
            store.get_fundamentals(
                ["AAPL"], "EPS", as_known_at="2026-02-01T00:00:00+00:00"
            )

    def test_universe_refusal(self, store):
        """G0.2c: get_universe raises PITViolation on future membership data."""
        store.insert_universe([
            dict(index_name="SP500", ticker="NEWCO",
                 as_of="2026-06-01T00:00:00+00:00",
                 available_at="2026-06-02T00:00:00+00:00",
                 pit_grade="native", in_index=True),
        ])
        with pytest.raises(PITViolation):
            store.get_universe("SP500", as_known_at="2026-05-01T00:00:00+00:00")

    def test_exactly_at_boundary_is_allowed(self, store):
        """available_at == as_known_at is allowed (not strictly future)."""
        ts = "2026-01-02T21:00:00+00:00"
        store.insert_price_bars([_bar(available_at=ts)])
        # Same timestamp — should NOT raise
        bars = store.get_price_bars(["AAPL"], as_known_at=ts)
        assert len(bars) == 1

    def test_violation_is_all_or_nothing(self, store):
        """If ANY row in the result would violate, the entire query is refused."""
        store.insert_price_bars([
            _bar(as_of="2026-01-01T00:00:00+00:00",
                 available_at="2026-01-01T21:00:00+00:00", close=148.0),  # OK
            _bar(as_of="2026-01-02T00:00:00+00:00",
                 available_at="2026-01-05T21:00:00+00:00", close=150.0),  # future
        ])
        # The first bar would be fine, but the second violates — entire query refused
        with pytest.raises(PITViolation):
            store.get_price_bars(["AAPL"], as_known_at="2026-01-03T00:00:00+00:00")

    def test_pitviol_exception_carries_timestamps(self, store):
        """PITViolation carries enough info for the audit log."""
        future_ts = "2026-06-15T00:00:00+00:00"
        store.insert_price_bars([_bar(available_at=future_ts)])

        with pytest.raises(PITViolation) as exc_info:
            store.get_price_bars(["AAPL"], as_known_at="2026-01-01T00:00:00+00:00")

        err = exc_info.value
        assert err.earliest_available_at == future_ts
        assert "2026-01-01" in err.as_known_at


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
