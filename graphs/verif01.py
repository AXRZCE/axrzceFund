"""VERIF-01 — deterministic memo validator (WP2, R3).

Validates a research memo against §2.1 `ResearchMemo` + the agent's §3 block, enforces the
§2 bounds the pydantic type alone does not (key_claims 3-7, thesis <=150 words), and strips
`fact` claims that cite no document (§1 rule 1 / P2 step 3). It **rejects a constructed bad
memo** — out-of-range conviction, missing required field, stray field, missing block, bad
cardinality, over-long thesis — so gutting it turns the tests red (anti-hoax contract).

WP2 scope is deterministic schema/citation validation (NO LLM call). VERIF-01's *LLM* duties —
claim-vs-document judging and debate scoring on a model family **different from the judged
agents** (§6.5, ADR-2) — land at WP3 where the debate makes them load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from graphs.state import FundMemo, ResearchMemo, SentMemo, TechMemo

# agent role -> the memo model (§2.1 base + the §3 block) it must conform to
MEMO_MODELS: dict[str, type[ResearchMemo]] = {
    "TECH-01": TechMemo,
    "FUND-TECH": FundMemo,
    "SENT-01": SentMemo,
}

MAX_THESIS_WORDS = 150          # §2.1
KEY_CLAIMS_MIN, KEY_CLAIMS_MAX = 3, 7  # §2.1


@dataclass
class VerificationResult:
    valid: bool
    schema_violations: list[str] = field(default_factory=list)
    stripped_claims: list[dict] = field(default_factory=list)


def _fmt_error(err: dict) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc or '<root>'}: {err.get('msg', 'invalid')}"


def verify_memo(raw: dict, *, agent_role: str) -> VerificationResult:
    """Validate `raw` against the memo contract for `agent_role`.

    `valid` reflects schema + §2 cardinality/length conformance. Uncited `fact` claims are
    reported in `stripped_claims` (a clean, not a reject — the caller applies P2's
    max-stripped-pct voiding policy).
    """
    model = MEMO_MODELS.get(agent_role)
    if model is None:
        return VerificationResult(
            valid=False,
            schema_violations=[f"unknown agent_role {agent_role!r} (have {sorted(MEMO_MODELS)})"],
        )

    try:
        memo = model.model_validate(raw)
    except ValidationError as e:
        return VerificationResult(valid=False, schema_violations=[_fmt_error(x) for x in e.errors()])

    violations: list[str] = []

    n = len(memo.key_claims)
    if not (KEY_CLAIMS_MIN <= n <= KEY_CLAIMS_MAX):
        violations.append(
            f"key_claims: {n} claims outside §2.1 bound [{KEY_CLAIMS_MIN},{KEY_CLAIMS_MAX}]"
        )

    words = len(memo.thesis.split())
    if words > MAX_THESIS_WORDS:
        violations.append(f"thesis: {words} words exceeds §2.1 cap ({MAX_THESIS_WORDS})")

    # §1 rule 1 / P2 step 3: a `fact` claim citing no doc_id is unsupported -> strip it.
    stripped: list[dict] = [
        {"claim": kc.claim, "reason": "fact claim cites no doc_id (§1 rule 1)"}
        for kc in memo.key_claims
        if kc.claim_type == "fact" and not kc.evidence
    ]

    return VerificationResult(valid=not violations, schema_violations=violations, stripped_claims=stripped)
