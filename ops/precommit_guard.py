#!/usr/bin/env python
"""Pre-commit guard: reject licensed VENDOR data from ever being committed (WP2 leak fix).

Vendor-agnostic — matches on the fixture/vendor-data PATH and SCHEMA, not any single vendor
(Sharadar prices+fundamentals, Alpaca IEX bars, Benzinga news). Our OWN outputs — reports,
orders, fills, computed stats — commit normally, because they don't carry the vendor-data
row-array shape.

HONEST LIMITATION: a LOCAL pre-commit hook only guards `git commit` on a machine where it's
installed (`git config core.hooksPath ops/git-hooks`). It is NOT a server-side gate: it can be
bypassed with `git commit --no-verify`, and a fresh clone that hasn't set core.hooksPath won't
run it. Adequate as *a* guard for a solo repo; it is not a substitute for repo-side controls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

# A vendor-data fixture/payload carries these row arrays (lists of row dicts).
VENDOR_ROW_KEYS = ("price_bars", "fundamentals", "news")
BLOCK_EXTENSIONS = (".parquet", ".duckdb")


def _has_vendor_row_arrays(d: dict) -> bool:
    for k in VENDOR_ROW_KEYS:
        v = d.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return True
    return False


def _looks_like_vendor_json(obj) -> bool:
    """A parsed JSON that looks like a vendor-data fixture: row arrays at top level or in a
    `payload` object. Our reports/orders/fills don't match (no such row arrays)."""
    if not isinstance(obj, dict):
        return False
    if _has_vendor_row_arrays(obj):
        return True
    payload = obj.get("payload")
    return isinstance(payload, dict) and _has_vendor_row_arrays(payload)


def is_vendor_data(path: str, content: bytes = b"") -> Optional[str]:
    """Return a reason string if `path` (+ `content` for JSON) is licensed vendor data that must
    not be committed, else None. `content` is only consulted for `.json` schema checks."""
    p = path.replace("\\", "/")
    # Always-allow: our code, and the tracked hash-locks (metadata + content_hash, no vendor values).
    if p.endswith(".py") or "/locks/" in p or p.endswith(".lock.json"):
        return None
    # Path rule: the fixture directories hold vendor data.
    if p.startswith("data/fixtures/"):
        return f"vendor-data fixture path: {p}"
    # Extension rule: raw vendor stores.
    if p.endswith(BLOCK_EXTENSIONS):
        return f"raw vendor-data file: {p}"
    # Schema rule: vendor-data shape anywhere (catches a leak committed outside data/fixtures/).
    if p.endswith(".json"):
        try:
            obj = json.loads(content.decode("utf-8", "replace"))
        except Exception:
            return None
        if _looks_like_vendor_json(obj):
            return f"vendor-data schema (price_bars/fundamentals/news rows): {p}"
    return None


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _staged_content(path: str) -> bytes:
    return subprocess.run(["git", "show", f":{path}"], capture_output=True).stdout


def main() -> int:
    violations: list[str] = []
    for path in _staged_files():
        content = _staged_content(path) if path.endswith(".json") else b""
        reason = is_vendor_data(path, content)
        if reason:
            violations.append(reason)
    if violations:
        sys.stderr.write("COMMIT BLOCKED — licensed vendor data must never be committed:\n")
        for v in violations:
            sys.stderr.write(f"  - {v}\n")
        sys.stderr.write(
            "Vendor data (Sharadar / Alpaca IEX / Benzinga) belongs in a gitignored fixture + a "
            "committed hash-lock (data/fixtures/locks/). Reports/orders/fills commit normally.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
