"""Stub agents — the ONLY legitimately-canned code in Phase 1 (brief §0).

Every stub is named `Stub<Role>`, lives only in this package, returns clearly-fake
memos, and is replaced by a real LLM agent in WP2. A canned return anywhere outside
`graphs/stubs/` is a hoax, not a stub. These exist so WP1 can prove the state
machine (checkpointing, kill/resume, fail-closed) with ZERO LLM spend.
"""

from graphs.stubs.agents import (
    StubBEAR01,
    StubBULL01,
    StubFUNDTECH,
    StubMOD01,
    StubPM01,
    StubPMORT01,
    StubSENT01,
    StubTECH01,
    StubVERIF01,
)

__all__ = [
    "StubFUNDTECH",
    "StubTECH01",
    "StubSENT01",
    "StubBULL01",
    "StubBEAR01",
    "StubMOD01",
    "StubPM01",
    "StubPMORT01",
    "StubVERIF01",
]
