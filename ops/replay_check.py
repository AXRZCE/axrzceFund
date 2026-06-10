"""G0.4 replay-determinism drill — validation-criteria.md G0.4, R4.

Rebuilds derived tables from one night's raw archive and verifies they match the
production PIT store BYTE-IDENTICALLY (canonical-JSON SHA256 per table, compared
over the replayed rows' primary keys).

Method:
  1. Load var/raw_archive/<run_id>/manifest.json; verify each parquet's SHA256
     against the manifest (archive integrity).
  2. Re-execute the SAME pure transforms (data/ingestion.py TRANSFORMS) with the
     ARCHIVED stamp, inserting into a fresh throwaway PIT store.
  3. For each table: canonical-serialize (sorted keys, sorted rows) the replica's
     rows AND the production rows matching the same primary keys; SHA256 both;
     require equality.

Timing caveat: nightly jobs upsert a trailing window, so a later night re-stamps
overlapping rows (same primary key, new available_at). The drill is therefore run
against the LATEST run_id, before the next nightly run overwrites its window —
which is also what "one sampled day" in G0.4 means.

Usage:  python ops/replay_check.py [run_id]     (default: latest archived run)
"""
import hashlib
import json
import logging
import sys
import tempfile
from pathlib import Path

import structlog

logging.basicConfig(level=logging.WARNING)
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

import pandas as pd

from data.ingestion import ARCHIVE_ROOT, TRANSFORMS, INSERTERS
from data.pit_store import PITStore

TABLE_KEYS = {
    "price_bars": ["ticker", "as_of", "source"],
    "fundamentals": ["ticker", "dimension", "period", "indicator", "available_at"],
    "universe_membership": ["index_name", "ticker", "as_of"],
    "corporate_actions": ["ticker", "as_of", "action"],
}


def canonical_hash(rows: list[dict]) -> str:
    """SHA256 of the sorted canonical-JSON serialization of a row set."""
    canon = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    return hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()


def fetch_rows(conn, table: str, keys: list[str], key_rows: list[tuple]) -> list[dict]:
    """Fetch table rows matching the given primary-key tuples, as dicts."""
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    if not key_rows:
        return []
    key_df = pd.DataFrame(key_rows, columns=keys)
    conn.register("replay_keys", key_df)
    on = " AND ".join(f"t.{k} = k.{k}" for k in keys)
    rows = conn.execute(
        f"SELECT t.* FROM {table} t JOIN replay_keys k ON {on}"
    ).fetchall()
    conn.unregister("replay_keys")
    return [dict(zip(cols, r)) for r in rows]


def main() -> int:
    runs = sorted(p.name for p in ARCHIVE_ROOT.iterdir() if (p / "manifest.json").exists()) \
        if ARCHIVE_ROOT.exists() else []
    if not runs:
        print("No raw archives found - run a nightly ingestion first.")
        return 1
    run_id = sys.argv[1] if len(sys.argv) > 1 else runs[-1]
    run_dir = ARCHIVE_ROOT / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"=== G0.4 REPLAY DRILL: {run_id} ===")

    # 1. Archive integrity
    for job, meta in manifest["jobs"].items():
        pq = run_dir / meta["file"]
        sha = hashlib.sha256(pq.read_bytes()).hexdigest()
        ok = sha == meta["sha256"]
        print(f"  archive  {job:<20} sha256 {'OK' if ok else 'MISMATCH'}")
        if not ok:
            return 1

    # 2. Rebuild into a fresh replica store
    tmp = Path(tempfile.mkdtemp())
    replica = PITStore(tmp / "replica.duckdb")
    replayed_keys: dict[str, set] = {t: set() for t in TABLE_KEYS}
    for job, meta in manifest["jobs"].items():
        table, transform = TRANSFORMS[job]
        df = pd.read_parquet(run_dir / meta["file"])
        rows = transform(df, meta["stamp"])
        if rows:
            getattr(replica, INSERTERS[table])(rows)
        print(f"  replay   {job:<20} {len(rows)} rows -> {table}")

    # 3. Compare per table: replica rows vs production rows at the same keys
    prod = PITStore()
    all_match = True
    comparisons = []
    for table, keys in TABLE_KEYS.items():
        rep_rows = [
            dict(zip([d[0] for d in replica.conn.execute(f"SELECT * FROM {table} LIMIT 0").description], r))
            for r in replica.conn.execute(f"SELECT * FROM {table}").fetchall()
        ]
        if not rep_rows:
            continue
        key_rows = [tuple(r[k] for k in keys) for r in rep_rows]
        prod_rows = fetch_rows(prod.conn, table, keys, key_rows)
        h_rep, h_prod = canonical_hash(rep_rows), canonical_hash(prod_rows)
        match = h_rep == h_prod
        all_match &= match
        comparisons.append({"table": table, "replica_rows": len(rep_rows),
                            "prod_rows": len(prod_rows), "hash": h_rep,
                            "match": match})
        print(f"  compare  {table:<20} replica={len(rep_rows)} prod={len(prod_rows)} "
              f"hash {'MATCH' if match else 'MISMATCH'} ({h_rep[:12]})")

    replica.close()
    prod.close()

    # Persist the drill artifact (G0.4 evidence)
    from datetime import datetime, timezone
    art_dir = Path("var/g04")
    art_dir.mkdir(parents=True, exist_ok=True)
    artifact = art_dir / f"replay_{run_id}.json"
    artifact.write_text(json.dumps({
        "run_id": run_id,
        "drilled_at": datetime.now(timezone.utc).isoformat(),
        "archive_integrity": "verified",
        "comparisons": comparisons,
        "pass": all_match,
    }, indent=2), encoding="utf-8")
    print(f"  artifact: {artifact}")

    print(f"\n  G0.4 VERDICT: {'PASS - byte-identical rebuild' if all_match else 'FAIL'}")
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
