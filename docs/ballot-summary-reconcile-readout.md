# R1 reconcile — `ballot_summary` schema (spec-vs-spec) + §2 sweep

**Branch:** `phase1/wp1-r1-ballot-summary-reconcile` · **Scope:** docs only, no code change
**Closes:** the one R1 deviation found in the WP1 review (agent-specifications §2 vs `graphs/state.py`).
**Discipline:** WP1 ruling R1 said *"if a §2 schema looks wrong, flag it (which-of-code/test/spec),
do not patch it."* This is that flag, resolved — by amending the **spec**, not the code.

## The finding (which-of-code/test/spec → **spec**)

The WP1 review flagged that code's `BallotSummary`
(`{weighted_score, margin, dissent_summary, contested}`) did not match
agent-specifications §2.3 (`{weighted_score, dissent}`). First read: "code drifted, conform it
down." That read was **wrong**, and a deeper check reversed it:

- **`decision-protocols.md:102` (P5 — the sealed ballot, the *authoritative* ballot mechanism)**
  defines its output as exactly `ballot_summary {weighted_score, margin, dissent_summary,
  contested: bool}`. The code matches **P5 field-for-field**.
- **`agent-specifications.md` §8 (Open Items, line 256)** explicitly defers ballot mechanics:
  *"Exact ballot mechanics and weight formula → decision-protocols.md."* So §2.3's two-field
  `ballot_summary` was never authoritative — it is an **abbreviated placeholder**, and the doc
  itself points to P5 for the real shape.
- **Config + downstream consumers depend on the richer shape:** `configuration.md:52`
  (`ballot_margin_threshold = 0.20` → margin < 20% = CONTESTED), `configuration.md:60`
  (`contested = ×0.5` sizing haircut, P6), P6 step 3 (`contested` → `contested_size_cap_pct_nav`),
  `glossary.md:73` (CONTESTED), `monitoring-metrics.md:49` (P5 margin histogram).

**Conclusion:** the code is faithful to the authoritative ballot spec (P5) + configuration;
agent-specifications §2.3 is the laggard. Conforming the code *down* would have **introduced**
drift — orphaning `ballot_margin_threshold`, the `contested` haircut, and
`contested_size_cap_pct_nav`, and desyncing the code from P5/P6. Per the brief
(spec-vs-spec conflict → stop and flag, do not "improve"), the fix is to bring the abbreviated
summary into line with the authority.

## The edits (docs only)

1. `agent-specifications.md` §2.3 (schema): `ballot_summary: {weighted_score, dissent}` →
   `{weighted_score: float, margin: float, dissent_summary: str, contested: bool}`, with a
   pointer that P5 is authoritative (reinforcing §8).
2. `agent-specifications.md` §5.1 (PM-01 guard prose): the field reference
   `ballot_summary.dissent` → `ballot_summary.dissent_summary` (the `dissent`→`dissent_summary`
   rename, so the override-rebuttal guard names the field the code/P5 actually carry). The English
   phrase "overriding strong dissent silently" is left as prose.

After this, **code + decision-protocols P5 + agent-specifications §2.3 + configuration all agree.**
No change to `graphs/state.py` (its `BallotSummary` and the `deep_loop.py` stub were already
P5-correct).

## §2 sweep (the broader check this reconcile triggered)

Lesson from the above: agent-specifications §2 can abbreviate the authoritative protocol specs.
So every §2 schema was re-audited against its protocol contract **and** the code:

| Schema | vs `graphs/state.py` | vs protocol | Verdict |
|---|---|---|---|
| §2.1 `ResearchMemo` | field-set matches | P2 adds no fields | clean |
| §2.2 `DebateTurn` | field-set matches | P4 adds no fields | clean |
| §2.3 `TradeProposal` | matches except `ballot_summary` | P6 OK | **`ballot_summary` only** (fixed above) |

`ballot_summary` was the **only** drift. Items deliberately **recorded, not fixed here** (out of
§2 scope; each belongs to a later WP):

- **WP2 (schema bar):** §2.1 cardinality (`key_claims` 3–7) and `thesis` ≤150 words are not yet
  enforced by the pydantic type — WP2 ruling 3 owns this. Per-agent memo blocks
  `technical_block` / `valuation_block` / `sentiment_block` (§3.4 / §3.2 / §3.5) must extend the
  memo schema per agent — the real WP2 schema-bar design point.
- **WP3:** code's `CycleState.debate_summary: Optional[str]` must become §4.2's structured object
  (`resolved_points`, `unresolved_cruxes`, `premortem`, `process_flags`) when MOD-01 is built;
  the debaters' `closing_statement` (§4.1) has no schema representation yet.

## Verification

Doc-only change; the audit above *is* the verification (field-by-field against P5/P6 + code, plus
a tree-wide `dissent` enumeration confirming exactly two reference sites). No test is affected
because no code changed; the existing WP1 suite (which constructs the already-correct
`BallotSummary`) remains green and is the standing guard that the code shape is P5-faithful.
