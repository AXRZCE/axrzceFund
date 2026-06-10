"""Tests for the PIT store — three-layer discipline (architecture.md L1).

G0.2 is split into two independent tests per validation-criteria.md:

  G0.2a (read-filter correctness, TestReadFilter):
    A query against a store containing rows spanning past AND future relative to
    as_known_at returns ONLY the past rows and does NOT throw.  This is the
    production path — backtesting 2015 against a store holding 2010-2023 must work.

  G0.2b (audit fires on future stamp, TestAuditFutureData):
    audit_future_data() detects rows with available_at > now() — the nightly
    tripwire that fires if the write guard was bypassed or data predates it.

Plus basic write-guard and CRUD tests.
"""

import gc
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from data.pit_store import PITStore, PITWriteError, PITAuditError


@pytest.fixture
def store():
    """Fresh in-memory-equivalent PIT store for each test."""
    tmpdir = tempfile.mkdtemp()
    s = PITStore(Path(tmpdir) / "pit.duckdb")
    try:
        yield s
    finally:
        s.close()
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Helper builders ────────────────────────────────────────────────────────────

def _past(days_ago: float = 1.0) -> str:
    """ISO UTC timestamp that is `days_ago` days in the past."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _future(days_ahead: float = 1.0) -> str:
    """ISO UTC timestamp that is `days_ahead` days in the future."""
    return (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()


def _bar(ticker="AAPL", as_of=None, available_at=None, close=150.0, source="sep"):
    as_of = as_of or _past(2)
    available_at = available_at or _past(1)
    return dict(ticker=ticker, as_of=as_of, available_at=available_at,
                pit_grade="ingestion-stamped", open=148.0, high=152.0,
                low=147.0, close=close, volume=10_000_000, source=source)


def _fund(ticker="AAPL", as_of=None, available_at=None, value=6.05):
    as_of = as_of or _past(30)
    available_at = available_at or _past(20)
    return dict(ticker=ticker, dimension="ARQ", period="2025Q4",
                as_of=as_of, available_at=available_at,
                pit_grade="native", indicator="EPS", value=value)


# ── Basic CRUD ─────────────────────────────────────────────────────────────────

class TestBasicCRUD:
    def test_insert_and_read_price_bars(self, store):
        store.insert_price_bars([_bar()])
        bars = store.get_price_bars(["AAPL"], as_known_at=_future(1))
        assert len(bars) == 1
        assert bars[0]["ticker"] == "AAPL"
        assert bars[0]["close"] == 150.0

    def test_insert_and_read_fundamentals(self, store):
        store.insert_fundamentals([_fund()])
        rows = store.get_fundamentals(["AAPL"], "EPS", as_known_at=_future(1))
        assert len(rows) == 1
        assert rows[0]["value"] == 6.05

    def test_insert_and_read_universe(self, store):
        store.insert_universe([
            dict(index_name="SP500", ticker="AAPL",
                 as_of=_past(2), available_at=_past(1),
                 pit_grade="native", in_index=True),
            dict(index_name="SP500", ticker="MSFT",
                 as_of=_past(2), available_at=_past(1),
                 pit_grade="native", in_index=True),
        ])
        universe = store.get_universe("SP500", as_known_at=_future(1))
        assert "AAPL" in universe
        assert "MSFT" in universe

    def test_staleness_check(self, store):
        store.insert_price_bars([_bar()])
        result = store.staleness_check("price_bars", max_age_hours=0.001)
        assert result["is_stale"] is True  # 0.001h threshold with yesterday's data

    def test_impossible_timestamps_rejected(self, store):
        """available_at < as_of is physically impossible."""
        with pytest.raises(ValueError, match="impossible"):
            store.insert_price_bars([
                _bar(as_of=_past(1), available_at=_past(2))
            ])


# ── Layer 2: Write guard ───────────────────────────────────────────────────────

class TestWriteGuard:
    """Layer 2: rows with available_at > now() are rejected at insert time."""

    def test_price_bars_future_available_at_rejected(self, store):
        """A bar claiming to be knowable tomorrow is always a bug."""
        with pytest.raises(PITWriteError) as exc_info:
            store.insert_price_bars([_bar(available_at=_future(1))])
        err = exc_info.value
        assert err.ticker == "AAPL"
        assert "future" in str(err).lower() or "wall-clock" in str(err).lower()

    def test_fundamentals_future_available_at_rejected(self, store):
        with pytest.raises(PITWriteError):
            store.insert_fundamentals([_fund(available_at=_future(30))])

    def test_universe_future_available_at_rejected(self, store):
        with pytest.raises(PITWriteError):
            store.insert_universe([
                dict(index_name="SP500", ticker="NEWCO",
                     as_of=_past(1), available_at=_future(1),
                     pit_grade="native", in_index=True)
            ])

    def test_past_available_at_accepted(self, store):
        """Normal past-stamped ingestion is accepted."""
        count = store.insert_price_bars([_bar(available_at=_past(1))])
        assert count == 1

    def test_exactly_now_is_accepted(self, store):
        """available_at == now() is accepted (boundary is exclusive)."""
        # We can't be exact to the nanosecond, but a very-recent past timestamp is fine
        count = store.insert_price_bars([_bar(available_at=_past(0.0001))])
        assert count == 1

    def test_write_error_carries_context(self, store):
        """PITWriteError carries ticker, available_at, and now for debugging."""
        future_ts = _future(5)
        with pytest.raises(PITWriteError) as exc_info:
            store.insert_price_bars([_bar(ticker="TSLA", available_at=future_ts)])
        err = exc_info.value
        assert err.ticker == "TSLA"
        assert err.available_at == future_ts
        assert err.now is not None


# ── Layer 1 — G0.2a: Read filter correctness ──────────────────────────────────

class TestReadFilter:
    """G0.2a: reads filter by available_at, never throw, work across mixed-age data.

    The production case: a store holding years of data is queried at a historical
    date.  Only rows knowable at that date are returned.  Future rows are silently
    excluded — no exception is raised.  This is what makes backtesting work.
    """

    def test_price_bars_filtered_by_as_known_at(self, store):
        """Mix of older and newer bars: query at midpoint returns only older ones."""
        older = _past(3)
        newer = _past(1)
        midpoint = _past(2)  # between older and newer

        store.insert_price_bars([
            _bar(as_of=_past(4), available_at=older, close=148.0),
            _bar(as_of=_past(2), available_at=newer, close=152.0),
        ])

        bars = store.get_price_bars(["AAPL"], as_known_at=midpoint)
        assert len(bars) == 1
        assert bars[0]["close"] == 148.0, "Only the older bar is visible at midpoint"

    def test_price_bars_no_exception_with_future_rows_in_store(self, store):
        """The defining G0.2a property: future rows in the store do NOT cause an exception.

        The write guard prevents truly future-stamped rows (available_at > now()) from
        entering.  But a 2024 bar is 'future' relative to a 2020 backtest query —
        that must silently filter, not throw.
        """
        bar_2020 = _bar(as_of=_past(2000), available_at=_past(1999), close=100.0)
        bar_2023 = _bar(as_of=_past(500),  available_at=_past(499),  close=175.0)

        store.insert_price_bars([bar_2020, bar_2023])

        # Query at 2020-equivalent horizon — sees only the 2020 bar, no exception
        bars_2020 = store.get_price_bars(
            ["AAPL"],
            as_known_at=_past(1000),  # between 1999 and 499 days ago
        )
        assert len(bars_2020) == 1
        assert bars_2020[0]["close"] == 100.0

        # Same store, later query — sees both bars, no exception
        bars_all = store.get_price_bars(["AAPL"], as_known_at=_past(1))
        assert len(bars_all) == 2

    def test_fundamentals_filtered_by_as_known_at(self, store):
        store.insert_fundamentals([
            _fund(as_of=_past(60), available_at=_past(50), value=5.0),
            _fund(as_of=_past(10), available_at=_past(5),  value=6.5),
        ])
        rows = store.get_fundamentals(["AAPL"], "EPS", as_known_at=_past(20))
        assert len(rows) == 1
        assert rows[0]["value"] == 5.0

    def test_universe_filtered_by_as_known_at(self, store):
        store.insert_universe([
            dict(index_name="SP500", ticker="AAPL",
                 as_of=_past(30), available_at=_past(29),
                 pit_grade="native", in_index=True),
        ])
        # Past query — sees the member
        assert "AAPL" in store.get_universe("SP500", as_known_at=_past(1))
        # Earlier query — member not yet knowable
        assert "AAPL" not in store.get_universe("SP500", as_known_at=_past(40))

    def test_empty_result_not_an_error(self, store):
        """When no rows fall within as_known_at, an empty list (not an exception) is returned."""
        store.insert_price_bars([_bar(available_at=_past(1))])
        bars = store.get_price_bars(["AAPL"], as_known_at=_past(5))
        assert bars == []

    def test_boundary_inclusive(self, store):
        """available_at == as_known_at is visible (boundary is inclusive)."""
        ts = _past(2)
        store.insert_price_bars([_bar(as_of=_past(3), available_at=ts, close=99.0)])
        bars = store.get_price_bars(["AAPL"], as_known_at=ts)
        assert len(bars) == 1
        assert bars[0]["close"] == 99.0


# ── Layer 3 — G0.2b: Nightly audit detects future stamps ──────────────────────

class TestAuditFutureData:
    """G0.2b: audit_future_data() is the nightly tripwire.

    It scans for available_at > now() — rows that bypassed the write guard or
    predate it.  Normal operation = empty list.  Violation = non-empty list.
    """

    def test_clean_store_returns_no_violations(self, store):
        store.insert_price_bars([_bar(available_at=_past(1))])
        violations = store.audit_future_data()
        assert violations == []

    def test_empty_store_returns_no_violations(self, store):
        violations = store.audit_future_data()
        assert violations == []

    def test_future_stamped_row_detected(self, store):
        """Force a future-stamped row into the store by bypassing the write guard,
        then confirm audit_future_data() catches it."""
        future_ts = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

        # Bypass the write guard via raw SQL (simulates a pre-guard ingest or bug)
        store.conn.execute(
            "INSERT OR REPLACE INTO price_bars "
            "(ticker, as_of, available_at, pit_grade, open, high, low, close, volume, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", _past(1), future_ts, "ingestion-stamped",
             148.0, 152.0, 147.0, 150.0, 1_000_000, "test"),
        )

        violations = store.audit_future_data()
        assert len(violations) == 1
        assert violations[0].table == "price_bars"
        assert violations[0].earliest_future_available_at == future_ts
        assert violations[0].row_count == 1

    def test_violation_error_carries_detail(self, store):
        """PITAuditError has enough info to log and alert."""
        future_ts = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        store.conn.execute(
            "INSERT OR REPLACE INTO fundamentals "
            "(ticker, dimension, period, as_of, available_at, pit_grade, indicator, value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "ARQ", "2025Q4", _past(30), future_ts, "native", "EPS", 6.0),
        )

        violations = store.audit_future_data()
        v = violations[0]
        assert v.table == "fundamentals"
        assert v.row_count >= 1
        assert "audit" in str(v).lower() or "future" in str(v).lower()

    def test_multiple_table_violations_all_reported(self, store):
        """If both price_bars and fundamentals have future rows, both are reported."""
        future_ts = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        store.conn.execute(
            "INSERT OR REPLACE INTO price_bars "
            "(ticker, as_of, available_at, pit_grade, open, high, low, close, volume, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", _past(1), future_ts, "ingestion-stamped",
             148.0, 152.0, 147.0, 150.0, 1_000_000, "test"),
        )
        store.conn.execute(
            "INSERT OR REPLACE INTO fundamentals "
            "(ticker, dimension, period, as_of, available_at, pit_grade, indicator, value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", "ARQ", "2025Q4", _past(30), future_ts, "native", "EPS", 6.0),
        )

        violations = store.audit_future_data()
        affected_tables = {v.table for v in violations}
        assert "price_bars" in affected_tables
        assert "fundamentals" in affected_tables


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
