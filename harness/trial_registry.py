"""Trial Registry — backtesting-framework.md §3.4.

The harness auto-logs every backtest configuration as a trial.
The API refuses to run any backtest without a registered trial_id.

This eliminates data dredging by ensuring:
- Every evaluated configuration is recorded (nothing swept under the rug)
- The true trial count N is available for DSR deflation
- Post-hoc cherry-picking is detectable by auditing the registry

Storage: SQLite (append-heavy, simple queries, no DuckDB needed here).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()

_STATUS_REGISTERED = "registered"
_STATUS_RUNNING = "running"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"

_VALID_STATUSES = {_STATUS_REGISTERED, _STATUS_RUNNING, _STATUS_COMPLETED, _STATUS_FAILED}
_VALID_EVIDENCE_CLASSES = {"E1", "E2", "E3", "E4"}


class UnregisteredTrialError(Exception):
    """Raised when code attempts to run a backtest without a registered trial_id."""


class TrialStateError(Exception):
    """Raised when a state transition is invalid (e.g., completing a registered trial)."""


@dataclass
class Trial:
    """A single registered trial (one backtest configuration evaluation)."""

    trial_id: str
    signal: str
    params: dict[str, Any]
    universe: str
    period_start: str
    period_end: str
    evidence_class: str
    hypothesis: str
    status: str
    registered_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: Optional[dict[str, Any]] = None
    error_msg: Optional[str] = None

    @property
    def params_hash(self) -> str:
        """Stable hash of (signal, params, universe, period) — used for dedup detection."""
        key = json.dumps(
            {
                "signal": self.signal,
                "params": self.params,
                "universe": self.universe,
                "period_start": self.period_start,
                "period_end": self.period_end,
            },
            sort_keys=True,
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class TrialRegistry:
    """SQLite-backed trial registry.

    Usage pattern:
        registry = TrialRegistry()

        # 1. Register before running anything
        trial_id = registry.register(
            signal="momentum_12_1",
            params={"lookback": 252, "skip": 21},
            universe="SP500",
            period_start="2010-01-01",
            period_end="2020-12-31",
            evidence_class="E2",
            hypothesis="12-1 momentum survives 2x costs over 2010-2020.",
        )

        # 2. Mark as running
        registry.start(trial_id)

        # 3. Run the actual backtest here ...

        # 4. Record results (or failure)
        registry.complete(trial_id, results={"sharpe": 0.82, "dsr": 0.61, "pbo": 0.18})
        # or: registry.fail(trial_id, error_msg="DivisionByZero in cost model")

        # DSR deflation input
        n, sharpes = registry.dsr_inputs(signal="momentum_12_1")
    """

    def __init__(self, db_path: Path | str = Path("var/trial_registry.db")):
        # ":memory:" → ephemeral in-memory registry (tests, per-run ensembles where
        # each run needs its own true trial count N without disk churn).
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = db_path
            self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trials (
                trial_id       TEXT PRIMARY KEY,
                signal         TEXT NOT NULL,
                params_json    TEXT NOT NULL,
                params_hash    TEXT NOT NULL,
                universe       TEXT NOT NULL,
                period_start   TEXT NOT NULL,
                period_end     TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                hypothesis     TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'registered',
                registered_at  TEXT NOT NULL,
                started_at     TEXT,
                completed_at   TEXT,
                results_json   TEXT,
                error_msg      TEXT
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal ON trials(signal)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON trials(status)"
        )
        self.conn.commit()

    # ── Write API ──────────────────────────────────────────────────────────

    def register(
        self,
        signal: str,
        params: dict[str, Any],
        universe: str,
        period_start: str,
        period_end: str,
        evidence_class: str,
        hypothesis: str,
    ) -> str:
        """Register a new trial and return its trial_id.

        Args:
            signal:         Signal/strategy identifier (e.g. 'momentum_12_1').
            params:         Parameterization dict (serializable to JSON).
            universe:       Universe name (e.g. 'SP500', 'NDX100').
            period_start:   Backtest start date (ISO YYYY-MM-DD).
            period_end:     Backtest end date (ISO YYYY-MM-DD).
            evidence_class: Must be E1, E2, E3, or E4.
            hypothesis:     One-sentence rationale for running this trial.

        Returns:
            trial_id string (used in all subsequent calls).

        Raises:
            ValueError: on invalid evidence_class or missing hypothesis.
        """
        if evidence_class not in _VALID_EVIDENCE_CLASSES:
            raise ValueError(
                f"evidence_class must be one of {_VALID_EVIDENCE_CLASSES}, got {evidence_class!r}"
            )
        if not hypothesis.strip():
            raise ValueError(
                "hypothesis is required — no rationale, no trial (backtesting-framework.md §3.5 rule 4)."
            )

        trial_id = f"trial_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(params, sort_keys=True)
        params_hash = hashlib.sha256(
            json.dumps(
                {"signal": signal, "params": params, "universe": universe,
                 "period_start": period_start, "period_end": period_end},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]

        self.conn.execute(
            """
            INSERT INTO trials
            (trial_id, signal, params_json, params_hash, universe,
             period_start, period_end, evidence_class, hypothesis,
             status, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (trial_id, signal, params_json, params_hash, universe,
             period_start, period_end, evidence_class, hypothesis,
             _STATUS_REGISTERED, now),
        )
        self.conn.commit()

        logger.info(
            "trial_registered",
            trial_id=trial_id, signal=signal, universe=universe,
            period_start=period_start, period_end=period_end,
            evidence_class=evidence_class,
        )
        return trial_id

    def start(self, trial_id: str) -> None:
        """Mark a trial as running. Must be called before the backtest executes.

        Raises:
            UnregisteredTrialError: if trial_id doesn't exist.
            TrialStateError: if not in 'registered' status.
        """
        trial = self._get_or_raise(trial_id)
        if trial["status"] != _STATUS_REGISTERED:
            raise TrialStateError(
                f"trial {trial_id} is in status '{trial['status']}'; "
                f"can only start a '{_STATUS_REGISTERED}' trial."
            )

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE trials SET status = ?, started_at = ? WHERE trial_id = ?",
            (_STATUS_RUNNING, now, trial_id),
        )
        self.conn.commit()
        logger.info("trial_started", trial_id=trial_id)

    def complete(self, trial_id: str, results: dict[str, Any]) -> None:
        """Record results and mark trial as completed.

        Args:
            trial_id: Must be in 'running' status.
            results:  Dict of result metrics (sharpe, dsr, pbo, etc.).

        Raises:
            UnregisteredTrialError: if trial_id doesn't exist.
            TrialStateError: if not in 'running' status.
        """
        trial = self._get_or_raise(trial_id)
        if trial["status"] != _STATUS_RUNNING:
            raise TrialStateError(
                f"trial {trial_id} is in status '{trial['status']}'; "
                f"can only complete a '{_STATUS_RUNNING}' trial."
            )

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE trials
            SET status = ?, completed_at = ?, results_json = ?
            WHERE trial_id = ?
            """,
            (_STATUS_COMPLETED, now, json.dumps(results, sort_keys=True), trial_id),
        )
        self.conn.commit()
        logger.info("trial_completed", trial_id=trial_id, results=results)

    def fail(self, trial_id: str, error_msg: str) -> None:
        """Mark a running trial as failed.

        Raises:
            UnregisteredTrialError: if trial_id doesn't exist.
            TrialStateError: if not in 'running' status.
        """
        trial = self._get_or_raise(trial_id)
        if trial["status"] != _STATUS_RUNNING:
            raise TrialStateError(
                f"trial {trial_id} is in status '{trial['status']}'; "
                f"can only fail a '{_STATUS_RUNNING}' trial."
            )

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE trials
            SET status = ?, completed_at = ?, error_msg = ?
            WHERE trial_id = ?
            """,
            (_STATUS_FAILED, now, error_msg, trial_id),
        )
        self.conn.commit()
        logger.warning("trial_failed", trial_id=trial_id, error_msg=error_msg)

    # ── Read API ───────────────────────────────────────────────────────────

    def get(self, trial_id: str) -> Trial:
        """Fetch a single trial by ID.

        Raises:
            UnregisteredTrialError: if not found.
        """
        row = self._get_or_raise(trial_id)
        return self._row_to_trial(row)

    def list_trials(
        self,
        signal: Optional[str] = None,
        status: Optional[str] = None,
        evidence_class: Optional[str] = None,
    ) -> list[Trial]:
        """List trials with optional filters."""
        query = "SELECT * FROM trials WHERE 1=1"
        params: list[Any] = []
        if signal:
            query += " AND signal = ?"
            params.append(signal)
        if status:
            query += " AND status = ?"
            params.append(status)
        if evidence_class:
            query += " AND evidence_class = ?"
            params.append(evidence_class)
        query += " ORDER BY registered_at DESC"

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_trial(r) for r in rows]

    def dsr_inputs(self, signal: Optional[str] = None) -> tuple[int, list[float]]:
        """Return (N_trials, list_of_sharpes) for DSR deflation.

        DSR requires the true trial count N and the distribution of Sharpe ratios
        across all completed trials.  Caller is responsible for the deflation formula.

        Args:
            signal: if given, restrict to that signal; otherwise all completed trials.

        Returns:
            (N, sharpes): N = total registered trials (incl. failed/running),
                          sharpes = Sharpe values from completed trials only.
        """
        query_n = "SELECT COUNT(*) FROM trials"
        query_sharpes = (
            "SELECT results_json FROM trials WHERE status = ? AND results_json IS NOT NULL"
        )

        base_params: list[Any] = []
        if signal:
            query_n += " WHERE signal = ?"
            query_sharpes += " AND signal = ?"
            base_params.append(signal)

        n_total = self.conn.execute(query_n, base_params).fetchone()[0]
        rows = self.conn.execute(
            query_sharpes, [_STATUS_COMPLETED] + base_params
        ).fetchall()

        sharpes = []
        for (rj,) in rows:
            try:
                r = json.loads(rj)
                if "sharpe" in r:
                    sharpes.append(float(r["sharpe"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        return n_total, sharpes

    def count_duplicate_configs(self) -> list[dict[str, Any]]:
        """Return configs that appear more than once (potential data dredging indicator)."""
        rows = self.conn.execute(
            """
            SELECT params_hash, signal, COUNT(*) as n
            FROM trials
            GROUP BY params_hash, signal
            HAVING n > 1
            ORDER BY n DESC
            """
        ).fetchall()
        return [{"params_hash": r[0], "signal": r[1], "count": r[2]} for r in rows]

    def require_trial_id(self, trial_id: str) -> Trial:
        """Gate check — call this at the top of any backtest entry point.

        Raises UnregisteredTrialError if trial_id is unknown or not in 'running' status.
        This is the enforcement mechanism: no trial_id, no backtest.
        """
        trial = self.get(trial_id)
        if trial.status != _STATUS_RUNNING:
            raise UnregisteredTrialError(
                f"trial {trial_id} has status '{trial.status}'; "
                f"call registry.start(trial_id) before running the backtest."
            )
        return trial

    def close(self) -> None:
        self.conn.close()

    # ── Internal helpers ───────────────────────────────────────────────────

    def _get_or_raise(self, trial_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM trials WHERE trial_id = ?", [trial_id]
        ).fetchone()
        if row is None:
            raise UnregisteredTrialError(
                f"trial_id '{trial_id}' not found in registry. "
                f"Register before running any backtest (backtesting-framework.md §3.4)."
            )
        return row

    @staticmethod
    def _row_to_trial(row: sqlite3.Row) -> Trial:
        return Trial(
            trial_id=row["trial_id"],
            signal=row["signal"],
            params=json.loads(row["params_json"]),
            universe=row["universe"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            evidence_class=row["evidence_class"],
            hypothesis=row["hypothesis"],
            status=row["status"],
            registered_at=row["registered_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            results=json.loads(row["results_json"]) if row["results_json"] else None,
            error_msg=row["error_msg"],
        )
