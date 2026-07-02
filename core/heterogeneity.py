"""Heterogeneity invariant — the decorrelation enforcement primitive (WP3 CP0).

configuration.md §3 and the Frozen Set §9.4 require decorrelated model families so no model
argues with, or judges, itself:
  - **Debate:** `family(BULL) != family(BEAR)` — else the debate is one family arguing with itself.
  - **Judge:** `family(judge) != family(judged)` — "where an alternative exists"
    (agent-specifications.md §6.5 VERIF-01 "Cannot judge its own family where an alternative exists").

This is a **Frozen-Set invariant**, so it is enforced in CODE and FAIL-CLOSED — not left to a
manifest comment (the manifest carries a `family` field but nothing there asserts the invariant).
Built once here as a shared primitive: the debate (R2) uses `assert_distinct_debaters`, and the
VERIF-01 judge (R6) reuses `assert_judge_disjoint` / `resolve_judge_family`.

Genuinely-no-alternative (a roster with a single family) is the one case where same-family judging
is permitted — but it is **LOGGED, never silent** (a run must be able to see it happened).
"""

from __future__ import annotations

from typing import Iterable

import structlog

logger = structlog.get_logger()


class HeterogeneityError(Exception):
    """A heterogeneity invariant was violated — same model family where distinct is required.
    Fail-closed: the caller must not proceed with a self-judging / self-arguing configuration."""


def assert_distinct_debaters(bull_family: str, bear_family: str) -> None:
    """Enforce `family(BULL) != family(BEAR)` (configuration.md §3, Frozen-Set §9.4).

    Raises HeterogeneityError if the two debate seats share a family — that debate would be one
    model family arguing with itself, defeating the decorrelation the debate exists to provide.
    With a >=2-family roster this is always satisfiable, so a same-family pair is a misconfiguration.
    """
    if bull_family == bear_family:
        raise HeterogeneityError(
            f"family(BULL) == family(BEAR) == {bull_family!r}: the debate would be one family "
            f"arguing with itself. Assign BULL and BEAR to distinct families (Frozen-Set §9.4)."
        )


def assert_judge_disjoint(
    judge_family: str, judged_family: str, available_families: Iterable[str]
) -> None:
    """Enforce `family(judge) != family(judged)` where a disjoint family is available (§6.5).

    - judge_family != judged_family        -> OK (return).
    - same family AND a disjoint family is available in `available_families` -> raise (fail-closed):
      a disjoint judge existed and was not used.
    - same family AND NO disjoint family is available -> permitted, but LOGGED (never silent).
    """
    if judge_family != judged_family:
        return
    disjoint = sorted(f for f in set(available_families) if f != judged_family)
    if disjoint:
        raise HeterogeneityError(
            f"judge family {judge_family!r} == judged {judged_family!r} while disjoint families "
            f"{disjoint} are available: judge != judged is required where an alternative exists "
            f"(agent-specifications.md §6.5). Route the judge to one of {disjoint}."
        )
    logger.warning(
        "judge_no_disjoint_family",
        judged_family=judged_family,
        note="no disjoint family available; judging same-family (logged, not silent)",
    )


def resolve_judge_family(judged_family: str, candidate_families: Iterable[str]) -> str:
    """Pick a judge family for `judged_family`: a disjoint family if one exists, else the judged
    family as a LOGGED no-alternative fallback (never silent). Deterministic (sorted) so replay is
    stable. This is the orchestrator's call-time resolver (R6); its output should still satisfy
    `assert_judge_disjoint`.
    """
    disjoint = sorted(f for f in set(candidate_families) if f != judged_family)
    if disjoint:
        return disjoint[0]
    logger.warning(
        "judge_no_disjoint_family",
        judged_family=judged_family,
        candidates=sorted(set(candidate_families)),
        note="no disjoint family available; falling back to same-family judge (logged, not silent)",
    )
    return judged_family
