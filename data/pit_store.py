"""Point-in-time (PIT) data store — architecture.md L1, ADR-6.

Every row has two timestamps:
  as_of        — event time: when the fact became true in the world
  available_at — knowledge time: when we could first have known it

All reads require an explicit `as_known_at` parameter.
The store physically refuses to return rows with available_at > as_known_at.
This single rule eliminates most look-ahead bias at the architecture level.

Storage: DuckDB (in-process) backed by Parquet files on disk.
Phase 1: single DuckDB database file in var/pit_store.duckdb.
"""

from __future__ import annotations

import duckdb
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

_LOOK_AHEAD_MSG = (
    "PIT violation: attempted to read data with available_at > as_known_at. "
    "This is architecture.md Principle 5 — the look-ahead threshold is zero, forever."
)


@dataclass
class PITViolation(Exception):
    """Raised when a query would read data not yet available at decision time."""
    as_known_at: str
    earliest_available_at: str

    def __str__(self) -> str:
        return (
            f"{_LOOK_AHEAD_MSG} "
            f"as_known_at={self.as_known_at}, "
            f"earliest_violation_available_at={self.earliest_available_at}"
        )


class PITStore:
    """Point-in-time data store backed by DuckDB.

    All data tables share the same schema contract:
      - as_of        TEXT NOT NULL  (ISO UTC)
      - available_at TEXT NOT NULL  (ISO UTC, >= as_of)
      - pit_grade    TEXT NOT NULL  ('native' | 'ingestion-stamped')
      - ... domain columns ...

    The store enforces the look-ahead rule at query time (not just at the app layer)
    so no bug in calling code can silently bypass it.
    """

    def __init__(self, db_path: Path = Path("var/pit_store.duckdb")):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = duckdb.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        """Create core tables if they don't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS price_bars (
                ticker        TEXT NOT NULL,
                as_of         TEXT NOT NULL,
                available_at  TEXT NOT NULL,
                pit_grade     TEXT NOT NULL DEFAULT 'ingestion-stamped',
                open          DOUBLE,
                high          DOUBLE,
                low           DOUBLE,
                close         DOUBLE,
                volume        BIGINT,
                source        TEXT,
                PRIMARY KEY (ticker, as_of, source)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals (
                ticker        TEXT NOT NULL,
                dimension     TEXT NOT NULL,
                period        TEXT NOT NULL,
                as_of         TEXT NOT NULL,
                available_at  TEXT NOT NULL,
                pit_grade     TEXT NOT NULL DEFAULT 'native',
                indicator     TEXT NOT NULL,
                value         DOUBLE,
                PRIMARY KEY (ticker, dimension, period, indicator, available_at)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS universe_membership (
                index_name    TEXT NOT NULL,
                ticker        TEXT NOT NULL,
                as_of         TEXT NOT NULL,
                available_at  TEXT NOT NULL,
                pit_grade     TEXT NOT NULL DEFAULT 'native',
                in_index      BOOLEAN NOT NULL,
                PRIMARY KEY (index_name, ticker, as_of)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_audit (
                run_id        TEXT NOT NULL,
                table_name    TEXT NOT NULL,
                run_ts        TEXT NOT NULL,
                rows_inserted BIGINT,
                rows_updated  BIGINT,
                source        TEXT,
                status        TEXT NOT NULL,
                error_msg     TEXT,
                PRIMARY KEY (run_id, table_name)
            )
        """)

    def _check_look_ahead(self, table: str, as_known_at: str) -> None:
        """Raise PITViolation if any row would violate the look-ahead rule.

        Called before every query that returns data.  We check first, return later —
        any violation aborts the query entirely (fail-closed).
        """
        result = self.conn.execute(
            f"""
            SELECT MIN(available_at) as earliest
            FROM {table}
            WHERE available_at > ?
            """,
            [as_known_at],
        ).fetchone()

        if result and result[0] is not None:
            raise PITViolation(
                as_known_at=as_known_at,
                earliest_available_at=result[0],
            )

    # ── Public read API ────────────────────────────────────────────────────

    def get_price_bars(
        self,
        tickers: list[str],
        as_known_at: str,
        start_date: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return daily price bars visible as of `as_known_at`.

        Args:
            tickers: List of ticker symbols.
            as_known_at: The decision_ts boundary (ISO UTC).
                         Rows with available_at > as_known_at are refused.
            start_date:  Optional earliest as_of date (ISO, inclusive).
            source:      Optional filter by source ('iex', 'sep', …).

        Returns:
            List of bar dicts ordered by (ticker, as_of).

        Raises:
            PITViolation: if any stored row for these tickers violates look-ahead.
        """
        self._check_look_ahead("price_bars", as_known_at)

        query = """
            SELECT ticker, as_of, available_at, pit_grade,
                   open, high, low, close, volume, source
            FROM price_bars
            WHERE ticker = ANY(?)
              AND available_at <= ?
        """
        params: list[Any] = [tickers, as_known_at]

        if start_date:
            query += " AND as_of >= ?"
            params.append(start_date)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY ticker, as_of"

        rows = self.conn.execute(query, params).fetchall()
        cols = ["ticker", "as_of", "available_at", "pit_grade",
                "open", "high", "low", "close", "volume", "source"]
        return [dict(zip(cols, r)) for r in rows]

    def get_fundamentals(
        self,
        tickers: list[str],
        indicator: str,
        as_known_at: str,
        dimension: str = "ARQ",
    ) -> list[dict[str, Any]]:
        """Return fundamental data visible as of `as_known_at`.

        Args:
            tickers:     Ticker symbols.
            indicator:   Sharadar SF1 indicator name (e.g. 'EPS', 'REVENUE').
            as_known_at: Decision timestamp boundary.
            dimension:   SF1 dimension (ARQ = as-reported quarterly, default).

        Returns:
            List of fundamental rows, one per (ticker, period, available_at).

        Raises:
            PITViolation: on look-ahead.
        """
        self._check_look_ahead("fundamentals", as_known_at)

        rows = self.conn.execute(
            """
            SELECT ticker, dimension, period, as_of, available_at,
                   pit_grade, indicator, value
            FROM fundamentals
            WHERE ticker = ANY(?)
              AND indicator = ?
              AND dimension = ?
              AND available_at <= ?
            ORDER BY ticker, available_at DESC
            """,
            [tickers, indicator, dimension, as_known_at],
        ).fetchall()

        cols = ["ticker", "dimension", "period", "as_of", "available_at",
                "pit_grade", "indicator", "value"]
        return [dict(zip(cols, r)) for r in rows]

    def get_universe(self, index_name: str, as_known_at: str) -> list[str]:
        """Return index constituents as of `as_known_at`.

        Args:
            index_name:  E.g. 'SP500'.
            as_known_at: Decision timestamp boundary.

        Returns:
            List of ticker symbols that were in the index at as_known_at.

        Raises:
            PITViolation: on look-ahead.
        """
        self._check_look_ahead("universe_membership", as_known_at)

        rows = self.conn.execute(
            """
            SELECT DISTINCT ON (ticker) ticker
            FROM universe_membership
            WHERE index_name = ?
              AND available_at <= ?
            ORDER BY ticker, available_at DESC
            """,
            [index_name, as_known_at],
        ).fetchall()

        # Keep only tickers where the latest known row has in_index = true
        result = []
        for (ticker,) in rows:
            row = self.conn.execute(
                """
                SELECT in_index FROM universe_membership
                WHERE index_name = ? AND ticker = ? AND available_at <= ?
                ORDER BY available_at DESC LIMIT 1
                """,
                [index_name, ticker, as_known_at],
            ).fetchone()
            if row and row[0]:
                result.append(ticker)

        return sorted(result)

    # ── Write API (used by ingestion jobs only) ────────────────────────────

    def insert_price_bars(self, rows: list[dict[str, Any]]) -> int:
        """Upsert price bars. Validates dual timestamps before insert.

        Args:
            rows: List of bar dicts with keys:
                  ticker, as_of, available_at, pit_grade,
                  open, high, low, close, volume, source.

        Returns:
            Number of rows inserted/updated.

        Raises:
            ValueError: if any row has available_at < as_of (impossible physics).
        """
        for r in rows:
            if r["available_at"] < r["as_of"]:
                raise ValueError(
                    f"available_at ({r['available_at']}) < as_of ({r['as_of']}) "
                    f"for ticker {r['ticker']} — impossible: knowledge can't precede event."
                )

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO price_bars
            (ticker, as_of, available_at, pit_grade, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r["ticker"], r["as_of"], r["available_at"], r.get("pit_grade", "ingestion-stamped"),
                 r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                 r.get("volume"), r.get("source"))
                for r in rows
            ],
        )
        logger.info("price_bars_inserted", count=len(rows))
        return len(rows)

    def insert_fundamentals(self, rows: list[dict[str, Any]]) -> int:
        """Upsert fundamental rows. Validates dual timestamps."""
        for r in rows:
            if r["available_at"] < r["as_of"]:
                raise ValueError(
                    f"available_at ({r['available_at']}) < as_of ({r['as_of']}) "
                    f"for ticker {r['ticker']} — impossible."
                )

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO fundamentals
            (ticker, dimension, period, as_of, available_at, pit_grade, indicator, value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r["ticker"], r["dimension"], r["period"],
                 r["as_of"], r["available_at"], r.get("pit_grade", "native"),
                 r["indicator"], r["value"])
                for r in rows
            ],
        )
        logger.info("fundamentals_inserted", count=len(rows))
        return len(rows)

    def insert_universe(self, rows: list[dict[str, Any]]) -> int:
        """Upsert universe membership rows."""
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO universe_membership
            (index_name, ticker, as_of, available_at, pit_grade, in_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (r["index_name"], r["ticker"], r["as_of"],
                 r["available_at"], r.get("pit_grade", "native"), r["in_index"])
                for r in rows
            ],
        )
        return len(rows)

    def record_ingestion(
        self,
        run_id: str,
        table_name: str,
        rows_inserted: int,
        source: str,
        status: str = "ok",
        error_msg: Optional[str] = None,
    ) -> None:
        """Log an ingestion run to the audit table."""
        run_ts = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT OR REPLACE INTO ingestion_audit
            (run_id, table_name, run_ts, rows_inserted, rows_updated, source, status, error_msg)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            [run_id, table_name, run_ts, rows_inserted, source, status, error_msg],
        )

    def staleness_check(
        self, table: str, max_age_hours: float = 26.0
    ) -> dict[str, Any]:
        """Check whether a table has been updated recently.

        Args:
            table:         Table name to check.
            max_age_hours: Alert threshold — default 26h catches a skipped nightly run.

        Returns:
            Dict with keys: table, latest_available_at, age_hours, is_stale.
        """
        row = self.conn.execute(
            f"SELECT MAX(available_at) FROM {table}"
        ).fetchone()

        latest = row[0] if row and row[0] else None
        now = datetime.now(timezone.utc).isoformat()

        if latest is None:
            return {"table": table, "latest_available_at": None,
                    "age_hours": None, "is_stale": True}

        from datetime import timedelta
        latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        age_hours = (now_dt - latest_dt).total_seconds() / 3600
        is_stale = age_hours > max_age_hours

        return {
            "table": table,
            "latest_available_at": latest,
            "age_hours": round(age_hours, 1),
            "is_stale": is_stale,
        }

    def close(self) -> None:
        self.conn.close()
