"""Stub agents — the ONLY legitimately-canned code in Phase 1 (brief §0).

Every stub is named `Stub<Role>`, lives only in this package, returns clearly-fake
memos, and leaves the package when its real agent lands. A canned return anywhere
outside `graphs/stubs/` is a hoax, not a stub. These exist so the skeleton can prove
the state machine (checkpointing, kill/resume, fail-closed) with ZERO LLM spend.

WP3 CP2: the debate stubs (StubBULL01/StubBEAR01/StubMOD01) left with graphs/debate.py;
StubPM01 no longer casts ballots (P5: PM does not vote) — StubVoters casts the skeleton's
deterministic sealed votes, tallied by the REAL graphs/ballot.tally.
"""

from graphs.stubs.agents import (
    StubFUNDTECH,
    StubPM01,
    StubPMORT01,
    StubSENT01,
    StubTECH01,
    StubVERIF01,
    StubVoters,
)

__all__ = [
    "StubFUNDTECH",
    "StubTECH01",
    "StubSENT01",
    "StubVoters",
    "StubPM01",
    "StubPMORT01",
    "StubVERIF01",
]
