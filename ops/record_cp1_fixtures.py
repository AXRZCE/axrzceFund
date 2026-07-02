#!/usr/bin/env python
"""Record the WP3 CP1 golden-day fixtures + write their committed hash-locks.

SPEND-FREE: reads the local canonical pit_store (var/pit_store.duckdb); makes NO LLM call. Re-runnable
on any box with the same Sharadar data — the `content_hash` in each lock is the reproducibility
contract (the licensed fixture itself stays gitignored; only the lock is committed).

Selection is PRE-DECLARED in docs/wp3-cp1-rubric.md:
  tickers    = AVGO, COST, MDT, LULU   (liquid S&P 500 across IT / Staples / Health-Care / Discretionary)
  indicators = ASSETS, EPS, EQUITY, FCF, NETINC, REVENUE   (dimension ARQ)
  days       = 2026-06-23..26          (each strictly AFTER the comparison binding cutoff, R1)
"""

from __future__ import annotations

from pathlib import Path

from core.manifest import load_manifest
from data.fixtures.harness import DEFAULT_FIXTURE_DIR, load_fixture, record_fixture, write_lock
from data.pit_store import PITStore

TICKERS = ["AVGO", "COST", "MDT", "LULU"]
INDICATORS = ["ASSETS", "EPS", "EQUITY", "FCF", "NETINC", "REVENUE"]
DAYS = ["2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"]
CMP_ROLES = ["BULL-01-CAND-DEEPSEEK", "BULL-01-CAND-GLM", "BULL-01-BASELINE-WEST"]


def main() -> None:
    store = PITStore()
    man = load_manifest()
    binding = man.binding_cutoff(CMP_ROLES)
    print(f"comparison roles     = {CMP_ROLES}")
    print(f"binding cutoff (MAX) = {binding}  (fixtures must be strictly after this — R1)")
    print(f"manifest_version     = {man.manifest_version}")
    for day in DAYS:
        decision_ts = f"{day}T20:00:00+00:00"
        fid = f"wp3_cp1_{day.replace('-', '')}"
        fx = record_fixture(
            store, fixture_id=fid, decision_ts=decision_ts, tickers=TICKERS,
            fundamentals_indicators=INDICATORS, fundamentals_dimension="ARQ",
        )
        # R1 sanity: the fixture must CLEAR the comparison binding cutoff or this raises FixtureGateError.
        load_fixture(DEFAULT_FIXTURE_DIR / f"{fid}.json", for_roles=CMP_ROLES, manifest=man)
        lock = write_lock(fx)
        print(f"  {fid}: decision_ts={decision_ts} price_bars={len(fx.payload['price_bars'])} "
              f"content_hash={fx.content_hash} -> {lock}")
    print("done — locks written to data/fixtures/locks/ (fixtures stay gitignored in data/fixtures/recorded/)")


if __name__ == "__main__":
    main()
