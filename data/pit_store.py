"""Point-in-time (PIT) data store — architecture.md L1, ADR-6.

Every row carries two timestamps:
  as_of        — event time: when the fact became true in the world
  available_at — knowledge time: when we could first have known it

Three-layer PIT discipline (architecture.md Principle 5):

  Layer 1 — Read filter (every read):
    All queries filter WHERE available_at <= as_known_at.  Future rows are
    silently excluded from results — they are not knowable at decision time.
    A 2018 backtest query against a store holding 2018-2023 data works correctly;
    it simply cannot see the 2019-2023 rows.  No exception is raised.

  Layer 2 — Write guard (every ingest):
    Any row with available_at > now() is rejected at insert time.  A row that
    claims to be knowable in the future is always a data bug (timezone error,
    vendor mislabel, parser mistake) — caught at the door, never stored.

  Layer 3 — Nightly audit (audit_future_data()):
    Scans all tables for available_at > now().  Should be silent in steady
    state; fires only if guard was bypassed or data predates the guard.
    Called by the nightly job; returns violations for the caller to handle.

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

_FUTURE_STAMP_MSG = (
    "PIT write guard: available_at is in the future of wall-clock. "
    "This row claims to be knowable before it exists — architecture.md Principle 5. "
    "This is always a data corruption or timezone bug at the ingestion source."
)

_AUDIT_VIOLATION_MSG = (
    "PIT audit violation: store contains rows with available_at > now(). "
    "Ingestion guard was bypassed or data predates the guard. "
    "Inspect ingestion logs — do not run backtests until resolved."
)


@dataclass
class PITWriteError(Exception):
    """Raised when an ingestion row has available_at > now() (future-stamped)."""
    ticker: str
    available_at: str
    now: str

    def __str__(self) -> str:
        return (
            f"{_FUTURE_STAMP_MSG} "
            f"ticker={self.ticker}, available_at={self.available_at}, now={self.now}"
        )


@dataclass
class PITAuditError(Exception):
    """Raised by audit_future_data() when future-stamped rows are found in the store."""
    table: str
    earliest_future_available_at: str
    row_count: int

    def __str__(self) -> str:
        return (
            f"{_AUDIT_VIOLATION_MSG} "
            f"table={self.table}, "
            f"earliest_future_available_at={self.earliest_future_available_at}, "
            f"rows_affected={self.row_count}"
        )


def to_utc_iso(ts: str) -> str:
    """Normalize any ISO-8601 timestamp string to canonical UTC form.

    Returns a fixed-width string: 'YYYY-MM-DDTHH:MM:SS.ffffff+00:00'.

    This is the keystone of the whole PIT store: every comparison it makes — the
    read filter (`available_at <= as_known_at`) and the write guard
    (`available_at > now()`) — is a *string* comparison on TEXT columns.  String
    comparison equals chronological comparison ONLY if every timestamp is in one
    canonical format and zone.  A row stamped '2026-06-10T15:00:00-04:00'
    (= 19:00 UTC) would otherwise lexicographically sort *before*
    '2026-06-10T18:46:30+00:00' and slip past both guards.  Normalizing at every
    boundary makes lexicographic order == chronological order, always.

    Handling:
      - 'Z' suffix accepted (and Python 3.11+ fromisoformat handles it natively).
      - Date-only strings ('2026-01-02') → midnight UTC.
      - Naive timestamps (no offset) → assumed UTC, per the store's documented
        contract that all timestamps are UTC (schema comment, configuration.md §10).
        Ingestion adapters own supplying the correct knowledge-time.
      - Offset-aware timestamps → converted to UTC.

    Raises:
        ValueError: if `ts` is not a parseable ISO-8601 string.
    """
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _utc_now_iso() -> str:
    """Canonical UTC 'now' in the same fixed-width form as to_utc_iso()."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


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
            CREATE TABLE IF NOT EXISTS corporate_actions (
                ticker        TEXT NOT NULL,
                as_of         TEXT NOT NULL,
                available_at  TEXT NOT NULL,
                pit_grade     TEXT NOT NULL DEFAULT 'ingestion-stamped',
                action        TEXT NOT NULL,
                value         DOUBLE,
                contraticker  TEXT,
                source        TEXT,
                PRIMARY KEY (ticker, as_of, action)
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

    def _check_write_guard(self, rows: list[dict], ticker_key: str = "ticker") -> None:
        """Raise PITWriteError if any row has available_at > now() (future-stamped).

        Called before every insert.  A row claiming to be knowable in the future is
        always a data bug (timezone error, vendor mislabel, parser mistake) — reject it
        at the door rather than letting it silently pollute the store.
        """
        now = _utc_now_iso()
        for r in rows:
            aa = to_utc_iso(r["available_at"])
            if aa > now:
                raise PITWriteError(
                    ticker=r.get(ticker_key, "?"),
                    available_at=aa,
                    now=now,
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

        Returns only rows with available_at <= as_known_at.  Future rows in the store
        are silently excluded — they are not knowable at decision time and are not an
        error; the nightly audit catches any that were incorrectly ingested.
        """
        query = """
            SELECT ticker, as_of, available_at, pit_grade,
                   open, high, low, close, volume, source
            FROM price_bars
            WHERE ticker = ANY(?)
              AND available_at <= ?
        """
        params: list[Any] = [tickers, to_utc_iso(as_known_at)]

        if start_date:
            query += " AND as_of >= ?"
            params.append(to_utc_iso(start_date))
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

        Returns only rows with available_at <= as_known_at.
        """
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
            [tickers, indicator, dimension, to_utc_iso(as_known_at)],
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

        Returns only tickers with available_at <= as_known_at.
        """
        known_at = to_utc_iso(as_known_at)
        rows = self.conn.execute(
            """
            SELECT DISTINCT ON (ticker) ticker
            FROM universe_membership
            WHERE index_name = ?
              AND available_at <= ?
            ORDER BY ticker, available_at DESC
            """,
            [index_name, known_at],
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
                [index_name, ticker, known_at],
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
            PITWriteError: if any row has available_at > now() (future-stamped).
            ValueError: if any row has available_at < as_of (impossible physics).
        """
        self._check_write_guard(rows)
        values = []
        for r in rows:
            as_of = to_utc_iso(r["as_of"])
            available_at = to_utc_iso(r["available_at"])
            if available_at < as_of:
                raise ValueError(
                    f"available_at ({available_at}) < as_of ({as_of}) "
                    f"for ticker {r['ticker']} — impossible: knowledge can't precede event."
                )
            values.append(
                (r["ticker"], as_of, available_at, r.get("pit_grade", "ingestion-stamped"),
                 r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                 r.get("volume"), r.get("source"))
            )

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO price_bars
            (ticker, as_of, available_at, pit_grade, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        logger.info("price_bars_inserted", count=len(rows))
        return len(rows)

    def insert_fundamentals(self, rows: list[dict[str, Any]]) -> int:
        """Upsert fundamental rows. Validates dual timestamps."""
        self._check_write_guard(rows)
        values = []
        for r in rows:
            as_of = to_utc_iso(r["as_of"])
            available_at = to_utc_iso(r["available_at"])
            if available_at < as_of:
                raise ValueError(
                    f"available_at ({available_at}) < as_of ({as_of}) "
                    f"for ticker {r['ticker']} — impossible."
                )
            values.append(
                (r["ticker"], r["dimension"], r["period"],
                 as_of, available_at, r.get("pit_grade", "native"),
                 r["indicator"], r["value"])
            )

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO fundamentals
            (ticker, dimension, period, as_of, available_at, pit_grade, indicator, value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        logger.info("fundamentals_inserted", count=len(rows))
        return len(rows)

    def insert_universe(self, rows: list[dict[str, Any]]) -> int:
        """Upsert universe membership rows."""
        self._check_write_guard(rows, ticker_key="ticker")
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO universe_membership
            (index_name, ticker, as_of, available_at, pit_grade, in_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (r["index_name"], r["ticker"], to_utc_iso(r["as_of"]),
                 to_utc_iso(r["available_at"]), r.get("pit_grade", "native"), r["in_index"])
                for r in rows
            ],
        )
        return len(rows)

    def insert_corporate_actions(self, rows: list[dict[str, Any]]) -> int:
        """Upsert corporate-action rows.

        Announcement semantics: corporate actions are the one data type where
        available_at < as_of is VALID — a split effective tomorrow (as_of in the
        future) is announced and knowable today (available_at = now). The
        available_at >= as_of physics check applies to MEASUREMENT data (a price
        bar can't be known before the bar closes) and is deliberately not applied
        here. The write guard (available_at <= now) and the read filter (on
        available_at) still hold, so PIT correctness is preserved: tomorrow's
        announced split is readable today precisely because we genuinely knew it.
        """
        self._check_write_guard(rows)
        values = []
        for r in rows:
            as_of = to_utc_iso(r["as_of"])
            available_at = to_utc_iso(r["available_at"])
            values.append(
                (r["ticker"], as_of, available_at,
                 r.get("pit_grade", "ingestion-stamped"), r["action"],
                 r.get("value"), r.get("contraticker"), r.get("source"))
            )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO corporate_actions
            (ticker, as_of, available_at, pit_grade, action, value, contraticker, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        logger.info("corporate_actions_inserted", count=len(rows))
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

    def audit_future_data(self) -> list["PITAuditError"]:
        """Scan all data tables for rows with available_at > now() (G0.2b nightly audit).

        These rows were either ingested before the write guard existed, or bypassed it.
        Returns a list of PITAuditError — one per affected table.  An empty list means
        the store is clean.  Callers decide whether to raise, log, or alert.

        Example (nightly cron):
            violations = store.audit_future_data()
            if violations:
                for v in violations:
                    logger.error("pit_audit_violation", detail=str(v))
                raise violations[0]   # halt ingestion pipeline
        """
        now = _utc_now_iso()
        tables = ["price_bars", "fundamentals", "universe_membership", "corporate_actions"]
        violations: list[PITAuditError] = []

        for table in tables:
            row = self.conn.execute(
                f"""
                SELECT MIN(available_at) as earliest, COUNT(*) as n
                FROM {table}
                WHERE available_at > ?
                """,
                [now],
            ).fetchone()

            if row and row[0] is not None:
                violations.append(
                    PITAuditError(
                        table=table,
                        earliest_future_available_at=row[0],
                        row_count=int(row[1]),
                    )
                )

        if not violations:
            logger.info("pit_audit_clean", tables_checked=len(tables), now=now)
        else:
            for v in violations:
                logger.error("pit_audit_violation", table=v.table,
                             earliest=v.earliest_future_available_at,
                             rows=v.row_count)
        return violations

    def close(self) -> None:
        self.conn.close()
