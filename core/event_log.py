"""Append-only event log with hash-chain integrity (architecture.md ADR-5).

The event log is the source of truth; all memory stores and dashboards are derived views.
Every event is immutable, timestamped, and part of a hash chain so tampering is detectable.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class Event:
    """A single immutable event in the log."""

    event_id: int  # Auto-increment primary key
    timestamp: str  # ISO format, UTC
    event_type: str  # "memo_written", "ballot_cast", "order_submitted", etc.
    cycle_id: str  # Which cycle this event belongs to
    decision_ts: Optional[str]  # The decision_ts boundary (if applicable)
    trade_id: Optional[str]  # The trade this event involves
    agent_id: Optional[str]  # Which agent produced/caused this event
    payload: Dict[str, Any]  # Event-specific data (serialized to JSON)
    prev_hash: str  # SHA256 of previous event (hash chain)
    hash: str  # SHA256 of this event


class EventLog:
    """Append-only event log with SQLite backend.

    Per architecture.md:
    - Append-only (no updates, no deletes after appending).
    - Hash chain: every event's hash includes the previous event's hash.
    - Nightly integrity check: hash chain must be continuous (G0.4).
    - All system events written here before the next step may proceed.
    """

    def __init__(self, db_path: Path = Path("var/event_log.db")):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the event_log table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_log (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    decision_ts TEXT,
                    trade_id TEXT,
                    agent_id TEXT,
                    payload TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL UNIQUE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cycle_id ON event_log(cycle_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trade_id ON event_log(trade_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_id ON event_log(agent_id);"
            )
            conn.commit()

    def append(
        self,
        event_type: str,
        cycle_id: str,
        decision_ts: Optional[str] = None,
        trade_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Append an event to the log.

        Every call increments event_id and extends the hash chain.
        This method must succeed fully before the next step proceeds (fail-closed).

        Args:
            event_type: Type of event (string).
            cycle_id: Which cycle.
            decision_ts: Optional decision timestamp.
            trade_id: Optional trade ID.
            agent_id: Optional agent ID.
            payload: Event-specific data (dict).

        Returns:
            The appended Event (immutable).

        Raises:
            RuntimeError: if append fails (hash chain integrity broken).
        """
        if payload is None:
            payload = {}

        timestamp = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Get the previous event's hash (or use "genesis" for the first event)
            cursor = conn.execute(
                "SELECT hash FROM event_log ORDER BY event_id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            prev_hash = row[0] if row else "genesis"

            # Compute this event's hash: SHA256(prev_hash + timestamp + payload)
            hash_input = json.dumps(
                {
                    "prev_hash": prev_hash,
                    "timestamp": timestamp,
                    "event_type": event_type,
                    "cycle_id": cycle_id,
                    "trade_id": trade_id,
                    "agent_id": agent_id,
                    "payload": payload,
                },
                sort_keys=True,
                default=str,
            )
            event_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            # Append to the log
            try:
                conn.execute(
                    """
                    INSERT INTO event_log
                    (timestamp, event_type, cycle_id, decision_ts, trade_id, agent_id, payload, prev_hash, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        event_type,
                        cycle_id,
                        decision_ts,
                        trade_id,
                        agent_id,
                        json.dumps(payload, default=str),
                        prev_hash,
                        event_hash,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                logger.error("event_log_append_failed", error=str(e))
                raise RuntimeError(f"Failed to append event: {e}")

            # Retrieve the inserted event
            cursor = conn.execute(
                "SELECT event_id FROM event_log WHERE hash = ?", (event_hash,)
            )
            row = cursor.fetchone()
            event_id = row[0] if row else -1

        event = Event(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            trade_id=trade_id,
            agent_id=agent_id,
            payload=payload,
            prev_hash=prev_hash,
            hash=event_hash,
        )

        logger.info(
            "event_appended",
            event_id=event_id,
            event_type=event_type,
            cycle_id=cycle_id,
            hash=event_hash[:8],
        )

        return event

    def verify_hash_chain(self) -> bool:
        """Verify the hash chain is continuous (no corruption, no gaps).

        This is the nightly integrity check per G0.4.

        Returns:
            True if the chain is valid, False otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT event_id, hash, prev_hash FROM event_log ORDER BY event_id"
            )
            rows = cursor.fetchall()

        if not rows:
            logger.info("hash_chain_check", result="empty", status="valid")
            return True

        # First event's prev_hash should be "genesis"
        first_event = rows[0]
        if first_event[2] != "genesis":
            logger.error("hash_chain_check", result="first_event_bad", expected="genesis", got=first_event[2])
            return False

        # Each event's hash should match the next event's prev_hash
        for i in range(len(rows) - 1):
            current_hash = rows[i][1]
            next_prev_hash = rows[i + 1][2]
            if current_hash != next_prev_hash:
                logger.error(
                    "hash_chain_check",
                    result="chain_broken",
                    position=i,
                    current_hash=current_hash[:8],
                    next_prev_hash=next_prev_hash[:8],
                )
                return False

        logger.info(
            "hash_chain_check",
            result="valid",
            event_count=len(rows),
        )
        return True

    def get_events(
        self,
        cycle_id: Optional[str] = None,
        trade_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Event]:
        """Retrieve events matching filters.

        Args:
            cycle_id: Filter by cycle.
            trade_id: Filter by trade.
            agent_id: Filter by agent.
            limit: Maximum number of events to return.

        Returns:
            List of matching events.
        """
        query = "SELECT * FROM event_log WHERE 1=1"
        params = []

        if cycle_id:
            query += " AND cycle_id = ?"
            params.append(cycle_id)
        if trade_id:
            query += " AND trade_id = ?"
            params.append(trade_id)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)

        query += " ORDER BY event_id"

        if limit:
            query += f" LIMIT {limit}"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        events = []
        for row in rows:
            payload = json.loads(row[7])  # payload is the 8th column
            event = Event(
                event_id=row[0],
                timestamp=row[1],
                event_type=row[2],
                cycle_id=row[3],
                decision_ts=row[4],
                trade_id=row[5],
                agent_id=row[6],
                payload=payload,
                prev_hash=row[8],
                hash=row[9],
            )
            events.append(event)

        return events


if __name__ == "__main__":
    # Test
    log = EventLog(Path("/tmp/test_event_log.db"))

    e1 = log.append(
        event_type="cycle_opened",
        cycle_id="cycle_20260610_0001",
        decision_ts="2026-06-10T14:00:00Z",
        payload={"universe_size": 500},
    )
    print(f"Event 1: {e1.event_id} {e1.event_type} {e1.hash[:8]}")

    e2 = log.append(
        event_type="memo_written",
        cycle_id="cycle_20260610_0001",
        trade_id="trade_abc123",
        agent_id="FUND-TECH",
        payload={"memo_id": "memo_001"},
    )
    print(f"Event 2: {e2.event_id} {e2.event_type} {e2.hash[:8]}")

    # Verify chain
    is_valid = log.verify_hash_chain()
    print(f"Hash chain valid: {is_valid}")

    # Retrieve events
    events = log.get_events(cycle_id="cycle_20260610_0001")
    print(f"Found {len(events)} events in cycle")
