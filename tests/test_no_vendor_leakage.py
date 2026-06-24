"""R5 enforcement (api-data-sources.md): vendor SDK imports (`alpaca`,
`nasdaqdatalink`) may appear ONLY under data/interfaces/. This is the gate that
keeps Phase 1 agent/protocol code from ever touching a vendor SDK directly.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ["core", "data", "harness", "graphs", "agents", "ops", "tests"]
# data/interfaces/: the adapters (the only production SDK site).
# tests/integration/: deliberate adapter-vs-raw-SDK equivalence checks that must
#   reference the vendor by their nature (test_adapter_equivalence.py) — gated
#   @pytest.mark.integration, out of the default run. Not a production path.
ALLOWED_PREFIXES = ("data/interfaces/", "tests/integration/")

# Matches a real import line for a vendor SDK at the start of a (possibly indented)
# line — not a mention inside a string or comment.
VENDOR_IMPORT = re.compile(r"^[ \t]*(?:import|from)[ \t]+(alpaca|nasdaqdatalink)\b", re.M)


def _py_files():
    for d in SEARCH_DIRS:
        root = REPO / d
        if root.exists():
            yield from root.rglob("*.py")


def test_vendor_sdk_imports_only_in_interfaces():
    leaks = []
    for p in _py_files():
        rel = p.relative_to(REPO).as_posix()
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        for m in VENDOR_IMPORT.finditer(p.read_text(encoding="utf-8")):
            leaks.append(f"{rel}: {m.group(0).strip()}")
    assert not leaks, (
        "R5 violation — vendor SDK imports outside data/interfaces/:\n" + "\n".join(leaks)
    )


def test_interfaces_actually_wrap_the_sdks():
    """Anti-hoax: 'no leakage' must not be achieved by wrapping nothing. The adapter
    modules must genuinely import the vendor SDKs."""
    iface = REPO / "data" / "interfaces"
    blob = "\n".join(
        (iface / f).read_text(encoding="utf-8") for f in ("alpaca.py", "sharadar.py")
    )
    assert VENDOR_IMPORT.search(blob), "adapters do not import any vendor SDK"
    assert "nasdaqdatalink" in blob and "alpaca" in blob
