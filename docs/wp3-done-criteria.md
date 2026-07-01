# WP3 — Debate + ballot + PM + shadow-ensemble: done-criteria + rulings

**Committed BEFORE implementation code** (phase1-completion-plan.md operating-discipline §1), like
WP1's seven and WP2's five. **Branch:** `phase1/wp3-debate`, based on **`origin/main`**. `phase1/wp2-wrapup`
is already merged into `main` (PR #4, merge `1d16338`); `origin/main` and `origin/phase1/wp2-wrapup` are
**byte-identical**, so there is nothing to merge (see SF-1, corrected).

**R-numbering convention:** per-WP, restarting at R1 (WP1 = R1–R7, WP2 = R1–R5). This is the **WP3
R-series, R1–R7**; refer to them as "WP3 R4" etc. in prose to avoid collision with earlier WPs'
same-numbered rulings.

**Binding specs (read-first, do not paraphrase):**
`phase1-completion-plan.md` §"WP3" (scope/components/gate);
`decision-protocols.md` P3 (debate-eligibility gate), **P4** (adversarial debate), **P5** (sealed
believability-weighted ballot — the tally formula and CONTESTED rule), **P6** (PM synthesis, override
rule, haircut stack);
`agent-specifications.md` §2.2 (DebateTurn), §2.3 (`TradeProposal.ballot_summary`, line 74), §4
(BULL-01/BEAR-01/MOD-01), §5.1 (**PM-01 guard, line 169**), §6.5 (**VERIF-01 judge, lines 224/230**),
§3 heterogeneity language;
`configuration.md` §3 (family/tier by role, T2_A/B/C map, T3 judge≠judged, **Frozen-Set §9.4
heterogeneity invariant**, ADR-2 amendment), §4 (`ballot_margin_threshold = 0.20`, weighting
disabled Phase 1–2), §5 (`contested = ×0.5` haircut, `contested_size_cap_pct_nav = 0.5%`,
`edge_to_cost_multiple = 3×`, `max_overrides_per_month = 2`);
`docs/ballot-summary-reconcile-readout.md` (the WP1-R1 four-field reconcile);
`backtesting-framework.md` §6 (C1 post-cutoff / C3 memorization probe — reused for the Chinese-family
golden-day validation).

**Goal.** Stand up the adversarial machinery on **real, decorrelated model families**: a genuinely
divergent bull/bear debate, a ballot whose `ballot_summary` is *computed from the actual votes*, the
contested/haircut mechanics that finally consume `ballot_margin_threshold`, a **replay-reproducible**
PM decision grounded in that ballot, VERIF-01 promoted to a **family-disjoint** LLM judge, and a
shadow-ensemble that **measures** decorrelation rather than assuming it. The Chinese open-weight family
(T2_A) — parked at WP2 — is fixture-validated here, and that validation **gates** the BULL seat.

> **Scope discipline.** WP3 builds P3→P6 + the VERIF-01 judge + the shadow-ensemble, **replacing the
> WP1 stubs** for `debate`, `ballot`, `pm`, and the judge path in `verify`. It does **not** build the
> risk gate / order manager (WP4), the learning loop / dashboard (WP5), or MACRO/QUANT (Phase 2). The
> P7 `risk_gate` node stays the WP1 stub until WP4.

---

## Ground truth this WP builds on (verified against fetched code on `origin/main` ≡ `phase1/wp2-wrapup`, not memory)

- **The four-field `ballot_summary` shape exists and is currently unread.** `BallotSummary`
  (`graphs/state.py:113`) = `{weighted_score, margin, dissent_summary, contested}`, matching
  `agent-specifications.md:74`. `CycleState.ballot_summary` (`state.py:167`) is `Optional`, and
  `TradeProposal.ballot_summary` (`state.py:132`) is **required**. In `graphs/deep_loop.py:135` the
  `ballot` node **hardcodes** `BallotSummary(weighted_score=0.5, margin=0.2, …)` — the P5 tally is
  *not computed from votes anywhere in the codebase*. WP3 makes P5 (`ballot-summary-reconcile`'s P5)
  finally real.
- **`Ballot` / `DebateTurn` / `debate_*` state fields exist** (`state.py:98,136,162–167`) but are only
  filled by stubs (`deep_loop.py:121–142`).
- **VERIF-01 is deterministic-only.** `graphs/verif01.py:8–11` explicitly defers claim-vs-document LLM
  judging and debate scoring **on a family different from the judged agents** to WP3.
- **The heterogeneity invariant is declared but unenforced in code.** `deploy/model_manifest.yaml`
  carries a `family` field per role and `core/manifest.py` resolves it, but **no code asserts**
  `family(BULL) ≠ family(BEAR)` or judge ≠ judged. It is a **Frozen-Set item** (configuration.md §9.4),
  so WP3 enforces it in code, fail-closed — not by config convention alone.
- **The manifest has only the 3 WP2 research roles.** No BULL-01/BEAR-01/MOD-01/PM-01 or a VERIF-judge
  role, no DeepSeek/GLM. WP3 adds them, each provider-pinned. Binding cutoff = `MAX` across a run's
  roles (`core/manifest.py:62`), currently `2026-03-05`.
- **The metered client already fails closed** on empty/degenerate replies (`core/llm.py:103–143`,
  tested by `tests/test_llm_client.py::test_degenerate_response_fails_closed`) and an agent `LLMError`
  already routes through the WP1 fail-closed router (`tests/test_deep_loop.py`, `FaultInjector(exc=…)`).
  Handoff §7(a) is therefore **substantially satisfied on this branch** (see Pre-debate prerequisites).

---

## Rulings (decided a priori — these are the bar; no post-hoc redefinition of "pass")

Every ruling names a **red test**: the concrete thing that, if the implementation is gutted, turns a
committed test red. Fixtures stay **gitignored**; only **hash-locks** and the committed *comparison
artifacts* land in git.

### R1 — Open-weight seat is evidence-gated (the Chinese-family fixture validation). *[gates everything]*
No Chinese open-weight model (DeepSeek V4-Pro / GLM-5.2, T2_A) takes the **BULL-01 seat** until a
**committed golden-day comparison** shows it meets the bar on **financial reasoning**, head-to-head
against the Western options, on the **same** fixtures. Three hard sub-conditions:
1. **Same-fixture, committed comparison.** DeepSeek V4-Pro and/or GLM-5.2 vs the Western fallback run
   the identical golden-day fixtures; the comparison (per-model memo/argument-quality scores, the bar,
   and the pass/fail verdict) is **committed** (the artifact, plus the fixtures' hash-locks — never the
   licensed fixture data). A missing/uncommitted comparison ⇒ the seat cannot be filled.
2. **Western-host pin, model ≠ host.** The chosen model is provider-pinned to a **Western inference
   host** (Fireworks / Together / Vertex on OpenRouter), `allow_fallbacks: false`, so no data leaves and
   `model_version` pins a frozen artifact. A manifest role whose model is Chinese-origin but whose
   `provider.only` is a non-Western host **fails to load** (fail-closed).
3. **Evidence-gated fallback.** If the open-weight model underperforms the bar on financial reasoning,
   the BULL seat **falls back to a Western frontier** — recorded as the comparison's verdict, not
   silently.
- *R1 depends on R1-of-WP2 (post-cutoff):* the golden-day fixtures must postdate the **binding cutoff
  including the Chinese model's own availability-date cutoff** (`core/manifest.py:62`). If a compared
  model shipped *after* the fixture date, that fixture cannot validate it — **verify at task start.**
- *Recommended backstop (backtesting §6 C3):* a memorization probe on the golden window before scoring;
  a model that recalls the period is disqualified for it. Build-if-cheap, flagged otherwise.
- **Red test:** a config/manifest that seats an **unvalidated** (or bar-failing) Chinese model in BULL
  fails a gating test; a **non-Western host** pin on a Chinese-origin model fails to load; the
  comparison artifact's absence fails the "seat is evidence-gated" test.

### R2 — Bull and Bear genuinely diverge (no self-agreement, no capitulation, grounded in the memos).
The debate produces **materially different** arguments from **different families** (Frozen-Set §9.4):
- **Divergence, measured.** BULL and BEAR take **opposing stances** and their arguments attack
  **different** memo claims / each other by reference (§2.2 `arguments[].attacks`). A BEAR turn that
  **agrees with the BULL** (same stance, or an empty/echoing `arguments` set, or a closing statement
  that concedes the thesis) is a **role violation → debate voided** (P4.2 capitulation rule), not a
  pass.
- **Grounded + bounded.** Debaters read **only** the post-VERIF verified memos + the opponent's prior
  turns (P4/isolation); arguments cite `doc_id`s; rounds are capped at `max_debate_rounds = 3`; MOD-01
  extracts a neutral `debate_summary` + a pre-mortem with **observable** early-warning indicators
  (§4.2), and carries no stance.
- **Red test:** inject a **sycophantic BEAR** (echoes the BULL / flips to agree) → the divergence check
  goes red and the debate is voided; a BULL and BEAR pinned to the **same family** fails the
  heterogeneity assertion (R6 shares this enforcement); a debater citing a memo not in the verified set
  fails the grounding check; a 4th round fails the round-cap test.

### R3 — Ballot integrity: `ballot_summary` is computed from the real votes (P5 tally), not asserted.
The `ballot` node **replaces the hardcoded stub** (`deep_loop.py:135`) with the P5 tally:
`weighted_score(d) = Σ_i w_i · conviction_i · 1[stance_i = d]` over the sealed `Ballot`s, with
**`w_i = 1` in Phase 1–2** (`weighting_enabled = false`, configuration.md §4 — equal weights until
track records exist). `margin` is the winner-vs-runner-up gap **normalized to total cast weight**
(decision-protocols P5.3 / configuration.md §4), and `dissent_summary` names the **actual** dissenting
voters/positions. `contested` is set by R4's rule.
- **Reflects the real debate:** the summary must change when the votes change; two different vote sets
  must yield **different** `ballot_summary`s.
- **Red test:** replace the tally with a hardcoded/canned `BallotSummary` (as the WP1 stub does) → a
  test that feeds two distinct vote sets and asserts distinct `weighted_score`/`margin`/`dissent`
  goes **red**; a `dissent_summary` that ignores a real dissenter fails.

### R4 — Contested mechanics actually fire (margin → contested → ×0.5 haircut **and** the cap).
When `margin < ballot_margin_threshold = 0.20` (of total cast weight), the ballot is **CONTESTED**
(`contested = True`). A contested ballot **must** cause, in the PM proposal (P6):
1. the **`contested = ×0.5`** size haircut (configuration.md §5, multiplicative-downward), **and**
2. the hard cap **`size_pct_nav ≤ contested_size_cap_pct_nav = 0.5%`** (configuration.md §5/§6).
Both fire; the cap binds even after the haircut. A non-contested ballot applies neither.
- **Red test:** a constructed **contested** ballot drives a PM proposal whose final `size_pct_nav` is
  **both** halved from its base **and** ≤ 0.5% NAV; gut either the haircut or the cap → the contested
  name is sized above 0.5% (or un-halved) → **red**. A borderline case at `margin = 0.20` exactly is
  pinned by an explicit boundary test (≥ threshold ⇒ not contested, per P5.3).

### R5 — PM-01 is replay-reproducible **and** grounded in `ballot_summary` (a canned PM fails).
PM-01 (Google / T2_C, third family) consumes the ballot and makes the final `TradeProposal` (§2.3):
- **Grounded in the ballot (guard, `agent-specifications.md:169`):** proposing **against** the weighted
  ballot direction requires an explicit **rebuttal in `ballot_summary.dissent_summary`**, and such
  overrides are capped at `max_overrides_per_month = 2` (P6.3) and tracked. A PM proposal that ignores
  a CONTESTED/dissenting ballot, or overrides without a rebuttal, is **invalid**.
- **Reproducible (WP2-R5 framing — no fake "LLM determinism"):** the PM decision is **reconstructable
  from the event log** (replay reads the stored decision; it does **not** re-call the LLM), and the
  **harness around the call is deterministic** — same fixture + same stored ballot/memos ⇒ same
  recorded proposal, same replay-compare (`CycleState.replay_comparable()`).
- **R5 deliverable — add `manifest_version` to the `ReplayTuple` (closes SF-2, confirmed real).**
  `core/replay.py`'s `ReplayTuple` currently carries only `agent_id, prompt_version, model_version,
  config_version, code_version, decision_ts` — **no `manifest_version`**, which contradicts
  phase1-completion-plan.md §5 and `core/manifest.py` ("stamped per call alongside `model_version`").
  WP3 **adds `manifest_version`** (the `deploy/model_manifest.yaml` hash) to the tuple, stamped on every
  metered call. **This must land BEFORE the Chinese-model BULL/BEAR/MOD/PM roles are added to the
  manifest** (SF-3), so a **roster swap is captured in the replay identity**. *Anti-hoax red test:* the
  **same decision replayed under a different manifest hash must yield a different replay identity** —
  gut the manifest stamping (drop or freeze the field) and that test goes **red**.
- **Red test:** a **canned PM decision** that ignores the ballot fails the grounding test; an override
  with no `dissent_summary` rebuttal fails the guard test; a replay that re-calls the LLM (instead of
  reading the stored decision), or drops the manifest/provider pin, or produces the **same replay
  identity across two different manifest hashes**, fails the reproducibility test.

### R6 — VERIF-01-as-judge is family-disjoint from the judged, **enforced in code, fail-closed.**
VERIF-01's WP2 deterministic validator is **retained**; WP3 adds T3 LLM claim/debate judging. The
orchestrator **resolves the judge's family at call time to be ≠ the judged agent's family**
(configuration.md §3 T3, `agent-specifications.md:230` "Cannot judge its own family where an
alternative exists"; Frozen-Set §9.4). This is **code enforcement**, not a manifest comment: a run that
would judge an agent with **its own family** — when a disjoint family is available — **raises / reroutes
fail-closed**; the genuinely-no-alternative case is **logged**, never silently same-family.
- **Red test:** force `family(judge) == family(judged)` with a disjoint family available → the resolver
  **raises** (or reroutes to a disjoint family), proven by a test; delete the disjointness check →
  same-family judging silently passes → **red**.

### R7 — Decorrelation is recorded and measured (shadow-ensemble), with **zero** live effect.
Additional families run **in shadow** on real decisions; each shadow family's **would-be decision is
logged** per cycle, and a **decorrelation metric is computed from those logs** (e.g., pairwise
stance/decision agreement across families) — decorrelation is **measured, not assumed** (seeds the
Phase-3 believability work). Shadow outputs **never** touch the live decision.
- **Red test:** the shadow decisions are logged and **distinct** from the live decision in the event
  log; removing the shadow-logging → the decorrelation-metric test goes **red** (nothing to measure);
  a shadow output that changes the live `decision`/`proposal` → the **isolation test goes red**.

---

## Build order (validation-gated first; the debate is wired onto the client only after the prerequisites)

**Pre-debate prerequisites (must land before any debate is wired — see phase1-completion-plan handoff §7):**
- **PRE-A — metered-client fail-open fix. DONE + TESTED (on `origin/main`).** `core/llm.py:103–143`
  retries then raises `LLMError` on an empty/degenerate reply;
  `test_llm_client.py::test_degenerate_response_fails_closed` is the inject-empty unit test;
  `test_deep_loop.py` proves an agent `LLMError` routes through the WP1 fail-closed router
  (`FaultInjector(exc=LLMError)`). **Confirm-only — no new code.**
- **PRE-B — VM git identity + push credential. DONE and WORKING (verified on `origin/main`).** Identity
  folded into `ops/vm_bootstrap.sh:28–31`; the push credential is proven live — `origin/main` `results/`
  holds the VM's autonomous commits: **G0.3 soak (18 consecutive clean nights through 2026-07-01)**,
  **G0.4 replay**, and **G0.5 broker round-trips (×2, real fills)**. **Rollup verdict (G0.3):** 18 ≥ the
  soak-ritual threshold ⇒ **PASS**. **No action needed** — WP3 can rely on autonomous result-commits.

**Then the WP3 task order (spend starts at task 1):**
1. **Chinese open-weight fixture-validation (R1)** — golden-day comparison, Western-host-pinned,
   committed, evidence-gated for the BULL seat. **[first paid task]**
2. **BULL-01 / BEAR-01 / MOD-01 debate (R2)** across the three decorrelated families (P4).
3. **Ballot + BallotSummary (R3)** — P5 tally consumed at last; replaces the `deep_loop.py:135` stub.
4. **Contested mechanics (R4)** — the haircut + cap fire on a contested ballot (P6).
5. **PM-01 (R5)** — grounded, replay-reproducible allocation (P6).
6. **VERIF-01-as-judge (R6)** — family-disjoint, enforced in code (§6.5).
7. **Shadow-ensemble (R7)** — decorrelation recorded/measured.

## Done — each demonstrable (not asserted)
- [ ] **R1** — committed golden-day comparison; Western-host pin enforced; BULL seat filled only on a
      passing verdict (or Western fallback recorded).
- [ ] **R2** — bull/bear divergence measured; sycophantic-bear injection voids the debate; same-family
      debaters fail; rounds ≤ 3; MOD-01 pre-mortem has observable indicators.
- [ ] **R3** — `ballot_summary` computed from the sealed votes; distinct votes ⇒ distinct summary;
      stub-hardcode replaced.
- [ ] **R4** — contested ballot ⇒ ×0.5 haircut **and** ≤ 0.5% cap in the PM proposal; boundary at 0.20.
- [ ] **R5** — PM grounded in the ballot (override needs a `dissent_summary` rebuttal); decision
      reconstructable from the event log; **`manifest_version` added to `ReplayTuple`** (different
      manifest hash ⇒ different replay identity — red-tested), landing **before** the new manifest roles.
- [ ] **R6** — judge family ≠ judged family, enforced in code, fail-closed; forced collision raises.
- [ ] **R7** — shadow decisions logged, distinct, measured for decorrelation, zero live effect.

## Anti-hoax checks (the human audits against these)
- **The gutting test, per ruling:** each ruling's "Red test" above is a committed, re-runnable test;
  removing/gutting the implementation turns it red. No `assert True`, no hardcoded `BallotSummary`, no
  canned PM decision, no config-only "enforcement".
- **No canned returns outside `graphs/stubs/`.** As WP3 replaces the `debate`/`ballot`/`pm`/judge
  stubs, those roles **leave** `graphs/stubs/`; a real agent returning a literal is a hoax, not a stub.
- **Decorrelation is proven, not claimed** — the shadow logs exist and the metric is computed from them.
- **Family-disjointness is code, not comment** — the manifest `family` field is not sufficient; a
  runtime assertion + fail-closed test is required (R2/R6).
- **Spend discipline:** every paid task reports actuals against the cap; the R1 validation is the first
  spend and reports per-model token/USD (feeds the G1.2d `≤ $8 p90 per decision` bar).
- Every artifact carries a `ReplayTuple`; every step emits its `Event`; hash-chain intact.

---

## Sequencing flags (raised now, not discovered mid-build)

- **SF-1 — Base branch. ~~RETRACTED~~ (corrected).** An earlier draft claimed the WP3 authority doc,
  `core/llm.py`, and `graphs/verif01.py` lived only on `phase1/wp2-wrapup`, not on `main`. That was a
  **stale-local-`main` error**: after `git fetch`, `origin/main` (`1d16338`, "Merge PR #4 from
  phase1/wp2-wrapup") and `origin/phase1/wp2-wrapup` (`e833741`) are **byte-identical** (empty recursive
  diff), all three files ARE on `origin/main`, and `e833741` is an ancestor of `origin/main`. **wp2-wrapup
  == main; nothing to merge.** `phase1/wp3-debate` is based directly on `origin/main`. No base-branch
  decision is needed.
- **SF-2 — `ReplayTuple` lacks `manifest_version` → PROMOTED to an R5 deliverable.** Confirmed real:
  `core/replay.py`'s `ReplayTuple` carries only `agent_id, prompt_version, model_version,
  config_version, code_version, decision_ts` — **no `manifest_version`**, contradicting plan §5. This is
  no longer just a flag; it is a **concrete R5 deliverable with an anti-hoax test** (see R5), and it
  **must land before the Chinese-model manifest roles are added** so a roster swap is captured in the
  replay identity.
- **SF-3 — Manifest roles + cutoffs for the new families.** BULL-01/BEAR-01/MOD-01/PM-01 and a
  VERIF-judge role must be **added to `deploy/model_manifest.yaml`** with per-model `cutoff`
  (availability-date proxy) and Western-host `provider` pins. Adding the Chinese model **raises the
  binding cutoff** for any fixture it reads — confirm the golden days still clear it (R1 dependency).
- **SF-4 — `manifest.py`/`model_manifest.yaml` cutoff wording drift.** `core/manifest.py` calls
  `cutoff` the "training-data cutoff"; the YAML header calls it the model's "public availability date"
  (a conservative upper bound). They reconcile (availability ≥ training cutoff), but the wording should
  be unified when the manifest is edited for SF-3 — cosmetic, not load-bearing.
- **SF-5 — VERIF-judge family resolution vs. a 3-family roster.** With only Google/OpenAI/Chinese in
  the roster, judging a Google agent (PM/MOD) leaves OpenAI/Chinese as disjoint judges; judging the
  Chinese BULL leaves Google/OpenAI. R6's "where an alternative exists" always has one here — but the
  resolver must **prove** it at call time, and log the (currently non-existent) no-alternative case.

## Standing rules carried from WP0–WP2 (unchanged)
Every load-bearing proof is a **committed, re-runnable test** (no deleted one-offs). Done-criteria
committed **before** code. WP ends with a readout in `docs/` + the events in `core/event_log.py` (the
event log is the source of truth). Provider pins stay `allow_fallbacks: false`, fail-closed. Fixtures
gitignored + hash-locked; the public-repo scrub holds. Branch + PR; **the human reads the PR — do not
self-merge.**

**Gate (Akshar).** ADR-2 amendment (done) + validated debating roster (R1) + genuine divergence (R2) +
computed ballot (R3) + firing contested mechanics (R4) + reproducible PM (R5) + family-disjoint judge
(R6) + recorded decorrelation (R7). No self-merge; no acceleration past the proof.
