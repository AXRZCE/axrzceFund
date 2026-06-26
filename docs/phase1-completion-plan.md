# axrzceFund — Phase 1 Completion Plan

Detailed execution brief covering the remainder of Phase 1: **WP2 (finish) → WP7 (go-live paper + G1 clock)**. This is the roadmap and scope with done-criteria targets and gates. It does **not** authorize skipping the per-WP discipline below.

---

## Operating discipline — applies to every WP

These are non-negotiable and unchanged from WP0–WP2:

1. **Done-criteria committed to git BEFORE implementation code.** Each WP opens with its rulings (R-series) and a `*-done-criteria.md` committed first; results are observed only after the bar is fixed.
2. **Anti-hoax contract.** Removing or gutting any implementation must turn its tests **red**. No `NotImplementedError`, `TODO`, hardcoded literal returns, or `assert True`. Load-bearing proofs are committed as re-runnable tests, never deleted one-offs. Legitimate stubs are quarantined in `graphs/stubs/` named `Stub*`.
3. **"Which of code / test / spec is wrong?"** before forcing any pass. When specs conflict, identify the authoritative source first (agent-specifications §2 owns schemas; decision-protocols owns mechanics).
4. **Each WP is built → verified → gated.** The Akshar merge is the gate; no self-merge, no acceleration. Later-WP done-criteria are *formalized when that WP starts*, informed by earlier-WP evidence — this plan fixes scope and targets, not the final committed criteria for WP4+.
5. **Replay identity stamped per call.** Every LLM decision records the ReplayTuple (`model_version` + `manifest_version` + provider pin + `decision_ts`) so it is byte-reproducible. Provider pins stay `allow_fallbacks: false`, fail-closed.
6. **Production runs on the VM (clawbot-v2); dev/review flows through git.** Agents read **committed fixtures**, not a live store. Anything the review side must verify (gate proofs, fixtures) is committed by the VM-side run, never left VM-only.

---

## Where we are (start of this plan)

| WP | Scope | Status |
|---|---|---|
| WP0 | Vendor interface adapters (R5 repay) | ✅ merged |
| WP1 | LangGraph deep-loop skeleton on stubs | ✅ merged |
| WP1-R1 | `ballot_summary` schema reconcile (→ P5) | ✅ merged |
| **WP2** | Real research agents vs post-cutoff fixtures | 🔨 **scaffolding + R1 gate + value-roster manifest + VERIF-01/§3 blocks done (149 green, $0 spend); metered client + agents remaining** |
| WP3 | Debate + ballot + PM + shadow-ensemble | ⬜ |
| WP4 | Risk gate + order manager + intraday monitor | ⬜ |
| WP5 | Learning loop + PMORT-01 + dashboard v1 | ⬜ |
| WP6 | Dry-run week (orders logged, not submitted) | ⬜ |
| WP7 | Go live on paper + open the G1 clock | ⬜ |

Roster on `main` (ADR-2 amendment, no Anthropic): FUND-TECH → `gemini-3.1-pro-preview` (google-vertex), TECH-01 → `gemini-2.5-flash-lite` (google-vertex), SENT-01 → `gpt-5.4` (openai). Binding fixture cutoff `2026-03-05`. Chinese open-weight family (DeepSeek/GLM, T2_A) parked for WP3.

---

## WP2 (finish) — Real research agents on post-cutoff fixtures

**Objective.** Prove the real-LLM research pipeline end to end against frozen, post-cutoff fixtures: a real call runs, is metered, is validated, is replay-stamped, and is provably grounded in its fixture.

**Remaining scope**

1. **Metered OpenRouter client (R4).** OpenAI-compatible client → OpenRouter. Wires each role's `provider` pin. Records real per-call token counts + USD cost into the decision record. *Anti-hoax:* gutting the metering (e.g., zeroing cost) turns a metering-assertion test red.
2. **FUND-TECH — first real call.** Record a June-2026 fixture (`decision_ts > 2026-03-05`); gate it (R1 post-cutoff); run Gemini 3.1 Pro through the client; validate the memo (R3 / VERIF-01); stamp the ReplayTuple (R5); prove grounded-in-fixture (a canned memo that ignores the fixture fails the grounding test). Spend cap ~$15, report actuals. **Record the fixture on the VM (where the pit_store data lives) and commit it**, so the agent reads a committed fixture wherever it runs.
3. **TECH-01.** Gated on the **SEP price backfill** (parallel prerequisite, ≥252d trailing history so its first memo isn't substantively hollow). Then run Gemini 2.5 Flash-Lite through the same gate → validate → stamp → grounding chain.
4. **SENT-01.** Needs a point-in-time news source — `DocumentsInterface.get_news` is ABC-only (the SENT-01 gap). Either implement a PIT-correct news source (then run GPT-5.4 through the chain) **or** record a logged defer ruling ("SENT-01 defers if no PIT news"). Do not fabricate a news path to make it pass.
5. **WP2 readout + PR.** Document the agents (or two + logged SENT defer), spend actuals, and the R1/R3/R4/R5 proofs with their anti-hoax confirmations.

**Done-criteria** (the 5 WP2 rulings, already committed). Completion bar: each in-scope research agent produces a **fixture-grounded, VERIF-01-validated, metered, replay-stamped** memo, with every anti-hoax test holding (gut any layer → red).

**Gate (Akshar).** Merge `phase1/wp2-agents` when the agents produce verified memos and the proofs hold.

**Parallel.** SEP backfill runs alongside FUND-TECH; it gates TECH-01 only, not FUND-TECH.

---

## WP3 — Debate + ballot + PM + shadow-ensemble

**Objective.** Stand up the adversarial machinery: real bull/bear debate across **decorrelated families**, a structured ballot, a reproducible PM decision, and a shadow-ensemble that measures whether the family diversity actually decorrelates. This is where the value roster's debating families — including the Chinese open-weight family — go live.

**Scope / components**

1. **Chinese open-weight family validation (the parked WP2 decision).** Before any Chinese model takes a debating seat: run DeepSeek V4-Pro (and/or GLM-5.2) against the **same golden-day financial fixtures** as the Western options, measure memo/argument quality head-to-head, and **commit the comparison**. Provider-pinned to a **Western host** (Fireworks / Together / Vertex on OpenRouter) so no data leaves and `model_version` pins a frozen artifact. If it underperforms on financial reasoning specifically, fall back to a Western frontier for that seat — the decision is evidence-gated, not assumed.
2. **Debaters + moderator (the three-family decorrelation).** Per ADR-2 (amended): BULL-01 (T2_A, the validated open-weight family), BEAR-01 (T2_B, OpenAI), MOD-01 (T2_C, Google) — three distinct families so no model argues with itself. Debate protocol per decision-protocols: bull thesis → bear rebuttal → bounded rounds → moderator adjudication, consuming WP2 research memos.
3. **Ballot + BallotSummary (P5 consumed at last).** Produce the four-field `ballot_summary` (`weighted_score`, `margin`, `dissent_summary`, `contested`) — the shape fixed in the WP1-R1 reconcile, now actually read. Wire the config §3 mechanics: `ballot_margin_threshold = 0.20`, the `contested × 0.5` size haircut, `contested_size_cap_pct_nav`. *Anti-hoax:* a contested ballot must actually trigger the haircut (gut it → red).
4. **PM-01 (portfolio manager).** Consumes the ballot, makes the final allocation. PM-01's guard reads `ballot_summary` (agent-specifications:168). Gemini 3.1 Pro. The decision is replay-stamped and reproducible.
5. **VERIF-01 becomes an LLM judge.** Its WP2 deterministic validator is retained; WP3 adds LLM claim/debate judging at the T3 tier, always a **different family than the agent being judged**.
6. **Shadow-ensemble.** Run additional families in shadow (no effect on the live decision), logging what each would have decided, to **measure decorrelation** on real decisions — validating the load-bearing assumption and seeding later believability work (Phase 3).

**Done-criteria targets** (formalize + commit at WP3 open): the debate produces genuinely divergent bull vs bear arguments (not one model agreeing with itself); the BallotSummary is structurally correct and reflects the actual debate; the contested/margin mechanics fire; the PM decision is replay-reproducible; VERIF-01-as-judge is family-disjoint from the judged; the Chinese-family validation is committed with its measured comparison; shadow-ensemble decorrelation is recorded.

**Anti-hoax.** Bull and Bear must produce real, different arguments; the ballot must reflect them (gut the scoring → red); the haircut must fire on contested ballots; a canned PM decision must fail the reproducibility/grounding tests.

**Gate (Akshar).** ADR-2 amendment (done) + validated debating roster + reproducible PM decision + recorded decorrelation.

---

## WP4 — Risk gate + order manager + intraday monitor

**Objective.** Add the risk-enforcement and (still-paper, still-unsubmitted) execution layer. Orders are **modeled/logged, never live**, until WP7.

**Scope / components**

1. **Risk gate (RISK-01).** Emotion-free, fail-closed enforcement of position limits, gross/net exposure caps, concentration limits, and the `contested_size_cap_pct_nav` (config §3 risk params). Vetoes or sizes-down any PM decision that breaches a limit. *Anti-hoax:* a decision that should breach must be blocked/sized-down (gut the gate → a breaching order passes → red).
2. **Order manager.** Translates the risk-approved PM decision into broker orders via `AlpacaBroker` (the WP0 write-path proven by G0.5). **Submission stays disabled** — orders are produced and logged, not sent. Sizing, rounding, and order-type logic are real and replay-stamped.
3. **Intraday monitor.** Consumes the Alpaca IEX live feed on the VM; watches positions/exposure during the session; fires risk responses (stop logic, exposure breaches) on simulated/real triggers. The deep-loop terminal node continues to emit `intended_order` as an event; WP4 builds the full order path behind the live-submission guard.

**Done-criteria targets** (formalize + commit at WP4 open): the risk gate provably blocks/sizes breaching decisions; the order manager produces correct orders from PM decisions (replay-stamped); the intraday monitor fires on injected breaches; **zero live submissions** (the dry-run guard holds and is tested). Precise numeric limits are set here informed by what the WP2–WP3 portfolio actually looks like — not pre-guessed.

**Gate (Akshar).** Risk gate + order manager + intraday monitor proven, no live submission.

---

## WP5 — Learning loop + PMORT-01 + dashboard v1

**Objective.** Add post-mortems, the feedback-to-memory loop, and first-version observability — the "instant post-mortem / total auditability" advantages made real.

**Scope / components**

1. **PMORT-01 (post-mortem agent).** Instant post-mortems on decisions/trades: outcome vs. thesis, P&L attribution, lessons. T3 tier, family-disjoint from the judged agent. *Anti-hoax:* a canned post-mortem that ignores the actual outcome fails its test.
2. **Learning loop.** Records decision outcomes and post-mortem lessons into agent memory (docs/memory-systems.md). This is the Phase-1 feedback substrate; **believability weighting itself is Phase 3** — do not build the weighting here, only the outcome/lesson capture it will later consume.
3. **Dashboard v1.** Renders the real decision record: candidate intake → research → debate → ballot → PM → risk → logged order → post-mortem, plus positions and P&L. Reads committed/real data, never mocked.

**Done-criteria targets** (formalize + commit at WP5 open): PMORT-01 produces real post-mortems tied to actual outcomes; the learning loop persists outcomes/lessons verifiably; the dashboard shows real data end to end.

**Gate (Akshar).** Post-mortem + learning capture + dashboard, all real.

---

## WP6 — Dry-run week (orders logged, not submitted)

**Objective.** Run the **whole fund** end-to-end, daily, on the VM, for a week — with orders **logged but not submitted** — to shake out operational stability and end-to-end correctness before any live-paper submission.

**Scope.** Full pipeline on systemd timers (`CRON_TZ=America/New_York`, `Persistent=true`): intake → research → debate → ballot → PM → risk → order manager (logged) → intraday monitor → post-mortem → dashboard, producing a complete, auditable decision record each cycle. Every artifact committed to git so the whole week is reviewable off-VM.

**Done-criteria targets** (formalize + commit at WP6 open): a full week of daily cycles completes on the VM; each cycle yields a complete, auditable, replay-deterministic record; **zero live orders**; replay determinism holds across the week; the dashboard reflects the week. This is the G1-readiness shakeout.

**Anti-hoax.** Orders logged, not submitted (guard tested); the week's records are real and reproducible; reboot/catch-up and timeout-killed runs are handled per the committed soak rulings.

**Gate (Akshar).** A clean dry-run week — no live orders, full auditability.

---

## WP7 — Go live on paper + open the G1 clock

**Objective.** Flip submission on to the **Alpaca paper account** (real paper trading, not live capital) and open the **G1 clock** — the ≥3-month continuous track record that the Phase-1 exit gate requires.

**Scope.** Enable live-paper submission through `AlpacaBroker` (the G0.5 write-path, now active in paper). Start the G1 record accumulating. Track validation-criteria **G1.1–G1.4** continuously. Full pipeline runs daily on the VM, auditable and replay-deterministic, with every cycle committed.

**Done-criteria targets** (formalize + commit at WP7 open): orders are actually submitted to Alpaca paper (verifiable via the broker), the submission guard is intentionally lifted (and that lift is itself logged/reviewed), the G1 clock starts, and G1.1–G1.4 metrics are tracked on a real, continuous, auditable record.

**Phase-1 EXIT gate.** **G1** — the ≥3-month paper record meeting G1.1–G1.4. This is the exit from Phase 1 and the entry condition for Phase 2 (Pods, Risk Depth, Signal Registry).

---

## Critical path & parallelism

- **Now → WP2 done:** metered client → FUND-TECH (first spend) → TECH-01 (after SEP backfill, ∥) → SENT-01 (news source or logged defer) → readout/PR.
- **SEP backfill** runs in parallel from now; gates TECH-01 only.
- **Chinese-family fixture validation** is the first WP3 task and gates the debating-roster finalization.
- **WP1-R1 `ballot_summary`** is consumed at WP3 — the reconcile must be merged before WP3 ballot work (it is).
- **G0.3 soak / G0.5 broker round-trip** proofs (the VM runs) are the closing Phase-0 evidence and the first production validation of the WP0 adapter refactor — pull from git and confirm committed/passing; verify the soak committed a proof to git, not VM-only.

## Open decisions — await evidence, don't front-run

- **WP3 debating-family final pick** (DeepSeek V4-Pro vs GLM-5.2 vs Western fallback for the Bull seat) — decided by the committed fixture-validation comparison, not assumed.
- **WP4 numeric risk limits** — set from the actual WP2–WP3 portfolio/position profile.
- **WP5 dashboard scope** — driven by what the decision record actually needs to surface.
- **SENT-01 news source vs. logged defer** — resolved within WP2 by whether a PIT-correct source lands.

---

*Discipline reminder: this plan fixes scope and gates. Each WP still opens with its own committed done-criteria and rulings, is verified against fetched code, and merges only on Akshar's gate. No step skips its gate; no phase accelerates past its proof.*
