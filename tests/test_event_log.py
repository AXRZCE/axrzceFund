"""Tests for the append-only event log with hash chain (architecture.md ADR-5)."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.event_log import EventLog, Event


@pytest.fixture
def temp_log():
    """Create a temporary event log for testing."""
    tmpdir = tempfile.mkdtemp()
    try:
        log = EventLog(Path(tmpdir) / "event_log.db")
        yield log
    finally:
        # Clean up: ensure all DB connections are closed
        import shutil
        import gc
        gc.collect()  # Force garbage collection to close SQLite connections
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass  # Windows SQLite lock issues


class TestEventLog:
    """Test append-only event log behavior."""

    def test_append_event(self, temp_log):
        """Append an event and verify it's stored."""
        event = temp_log.append(
            event_type="test_event",
            cycle_id="cycle_001",
            payload={"data": "test"},
        )

        assert event.event_id == 1
        assert event.event_type == "test_event"
        assert event.cycle_id == "cycle_001"
        assert event.prev_hash == "genesis"
        assert len(event.hash) == 64  # SHA256 is 64 hex chars

    def test_append_multiple_events(self, temp_log):
        """Append multiple events and verify hash chain."""
        e1 = temp_log.append(
            event_type="event_1",
            cycle_id="cycle_001",
            payload={"num": 1},
        )
        e2 = temp_log.append(
            event_type="event_2",
            cycle_id="cycle_001",
            payload={"num": 2},
        )
        e3 = temp_log.append(
            event_type="event_3",
            cycle_id="cycle_001",
            payload={"num": 3},
        )

        # Each event's prev_hash should match the previous event's hash
        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash

        # All hashes should be unique
        hashes = {e1.hash, e2.hash, e3.hash}
        assert len(hashes) == 3

    def test_verify_hash_chain_valid(self, temp_log):
        """Verify an intact hash chain."""
        temp_log.append(event_type="e1", cycle_id="cycle_001", payload={})
        temp_log.append(event_type="e2", cycle_id="cycle_001", payload={})
        temp_log.append(event_type="e3", cycle_id="cycle_001", payload={})

        is_valid = temp_log.verify_hash_chain()
        assert is_valid, "Hash chain should be valid"

    def test_verify_hash_chain_detects_tampering(self, temp_log):
        """Verify that hash chain detects tampering."""
        temp_log.append(event_type="e1", cycle_id="cycle_001", payload={})
        temp_log.append(event_type="e2", cycle_id="cycle_001", payload={})

        # Manually corrupt an event in the database
        with sqlite3.connect(temp_log.db_path) as conn:
            conn.execute("UPDATE event_log SET hash = ? WHERE event_id = 1", ("corrupted",))
            conn.commit()

        is_valid = temp_log.verify_hash_chain()
        assert not is_valid, "Hash chain should detect tampering"

    def test_get_events_filter_by_cycle(self, temp_log):
        """Filter events by cycle_id."""
        temp_log.append(event_type="e1", cycle_id="cycle_001", payload={})
        temp_log.append(event_type="e2", cycle_id="cycle_002", payload={})
        temp_log.append(event_type="e3", cycle_id="cycle_001", payload={})

        events_c1 = temp_log.get_events(cycle_id="cycle_001")
        events_c2 = temp_log.get_events(cycle_id="cycle_002")

        assert len(events_c1) == 2
        assert len(events_c2) == 1
        assert all(e.cycle_id == "cycle_001" for e in events_c1)

    def test_get_events_filter_by_trade(self, temp_log):
        """Filter events by trade_id."""
        temp_log.append(
            event_type="e1",
            cycle_id="cycle_001",
            trade_id="trade_001",
            payload={},
        )
        temp_log.append(
            event_type="e2",
            cycle_id="cycle_001",
            trade_id="trade_002",
            payload={},
        )

        events_t1 = temp_log.get_events(trade_id="trade_001")
        assert len(events_t1) == 1
        assert events_t1[0].trade_id == "trade_001"

    def test_get_events_filter_by_agent(self, temp_log):
        """Filter events by agent_id."""
        temp_log.append(
            event_type="e1",
            cycle_id="cycle_001",
            agent_id="FUND-TECH",
            payload={},
        )
        temp_log.append(
            event_type="e2",
            cycle_id="cycle_001",
            agent_id="BULL-01",
            payload={},
        )

        events_fund = temp_log.get_events(agent_id="FUND-TECH")
        assert len(events_fund) == 1
        assert events_fund[0].agent_id == "FUND-TECH"

    def test_empty_log(self, temp_log):
        """Verify an empty log passes hash chain check."""
        is_valid = temp_log.verify_hash_chain()
        assert is_valid, "Empty log should be valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
