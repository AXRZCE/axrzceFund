"""Golden-day fixture harness + R1 post-cutoff gate (WP2).

A fixture freezes the point-in-time data an agent reads for one historical trading day
(`decision_ts`) into a replayable bundle, sourced ONLY through `data/pit_store.py` at
`as_known_at = decision_ts` (so it contains no look-ahead rows by construction — R2).

R1 (the hardest-to-fake proof, = backtesting-framework.md §6 C1): `load_fixture` REJECTS any
fixture whose `decision_ts` is at or before the binding training-data cutoff of the model(s)
that will read it. The gate is on the information-boundary date (`decision_ts`), never the
record date. No real LLM call runs against a fixture that has not passed this gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import structlog

from core.manifest import Manifest
from data.pit_store import PITStore, to_utc_iso

logger = structlog.get_logger()

DEFAULT_FIXTURE_DIR = Path("data/fixtures/recorded")


class FixtureGateError(Exception):
    """R1 rejection: a fixture's decision_ts is at/before the binding training-data cutoff
    of the model(s) that would read it — a pre-cutoff day risks memorization."""


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    decision_ts: str          # information boundary — the gate's subject
    tickers: list[str]
    payload: dict[str, Any]   # {"price_bars": [...], "fundamentals": {indicator: [...]}}
    content_hash: str
    recorded_at: str          # record time — explicitly NOT the gate's subject
    source: str

    @property
    def decision_date(self) -> date:
        return datetime.fromisoformat(to_utc_iso(self.decision_ts)).date()

    def audit_lookahead(self) -> list[dict[str, Any]]:
        """R2 look-ahead audit over the frozen reads: every row's `available_at` must be
        <= `decision_ts`. Returns offending rows (empty == clean). Clean by construction
        because the reads went through `pit_store` as-of `decision_ts`; this re-checks it."""
        boundary = to_utc_iso(self.decision_ts)
        bad: list[dict[str, Any]] = []
        for row in self.payload.get("price_bars", []):
            if to_utc_iso(row["available_at"]) > boundary:
                bad.append(row)
        for ind_rows in self.payload.get("fundamentals", {}).values():
            for row in ind_rows:
                if to_utc_iso(row["available_at"]) > boundary:
                    bad.append(row)
        return bad

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Fixture":
        return cls(
            fixture_id=d["fixture_id"],
            decision_ts=d["decision_ts"],
            tickers=list(d["tickers"]),
            payload=d["payload"],
            content_hash=d["content_hash"],
            recorded_at=d["recorded_at"],
            source=d.get("source", "pit_store"),
        )


def record_fixture(
    store: PITStore,
    fixture_id: str,
    decision_ts: str,
    tickers: list[str],
    *,
    fundamentals_indicators: Optional[Iterable[str]] = None,
    fundamentals_dimension: str = "ARQ",
    out_dir: Path = DEFAULT_FIXTURE_DIR,
) -> Fixture:
    """Freeze the PIT reads for `tickers` as-of `decision_ts` into a fixture file.

    Recording is allowed for ANY day — the post-cutoff gate is enforced at LOAD/use time
    (`load_fixture`), not here. You may legitimately record a pre-cutoff day; it simply can
    never feed a real LLM call.
    """
    price_bars = store.get_price_bars(tickers, as_known_at=decision_ts)
    fundamentals: dict[str, list[dict[str, Any]]] = {}
    for ind in fundamentals_indicators or []:
        fundamentals[ind] = store.get_fundamentals(
            tickers, ind, as_known_at=decision_ts, dimension=fundamentals_dimension
        )

    payload = {"price_bars": price_bars, "fundamentals": fundamentals}
    content_hash = hashlib.sha256(
        _canonical(
            {"decision_ts": to_utc_iso(decision_ts), "tickers": sorted(tickers), "payload": payload}
        ).encode()
    ).hexdigest()[:16]

    fx = Fixture(
        fixture_id=fixture_id,
        decision_ts=decision_ts,
        tickers=sorted(tickers),
        payload=payload,
        content_hash=content_hash,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        source="pit_store",
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{fixture_id}.json").write_text(fx.to_json())
    logger.info(
        "fixture_recorded", fixture_id=fixture_id, decision_ts=decision_ts,
        tickers=len(tickers), price_rows=len(price_bars), hash=content_hash,
    )
    return fx


def load_fixture(path: Path, *, for_roles: list[str], manifest: Manifest) -> Fixture:
    """Load a fixture and ENFORCE R1: `decision_ts` must be strictly after the binding
    training-data cutoff of `for_roles`. Raises FixtureGateError otherwise.

    This is the single chokepoint every real LLM run must pass through.
    """
    fx = Fixture.from_dict(json.loads(Path(path).read_text()))
    binding = manifest.binding_cutoff(for_roles)
    if fx.decision_date <= binding:
        raise FixtureGateError(
            f"R1 reject: fixture {fx.fixture_id!r} decision_ts={fx.decision_ts} "
            f"(date {fx.decision_date}) is at/before the binding training-data cutoff {binding} "
            f"for roles {for_roles} — a pre-cutoff day risks memorization (backtesting §6 C1). "
            f"No LLM call may run against it."
        )
    logger.info(
        "fixture_gate_pass", fixture_id=fx.fixture_id, decision_date=str(fx.decision_date),
        binding_cutoff=str(binding), roles=for_roles, manifest_version=manifest.manifest_version,
    )
    return fx
