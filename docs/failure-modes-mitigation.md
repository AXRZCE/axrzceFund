# failure-modes-mitigation.md — The Consolidated Risk Registry: What Can Go Wrong, How We Catch It, What We Do

**Status:** v1.0 — Tier 3 document
**Depends on:** every prior doc (this consolidates their scattered defenses into one auditable registry)
**Format per entry:** failure mode — *detection signal (named metric/audit)* — **mitigation (mechanism + doc ref)** — residual risk we still carry.
**Honesty rule:** §7 lists risks we have consciously accepted rather than mitigated. A registry with no accepted risks is lying.

---

## 1. LLM & Agent Failure Modes

| # | Failure | Detection | Mitigation | Residual |
|---|---|---|---|---|
| 1.1 | **Sycophancy / conformity** — agents converge on the confident voice, not the right one | D3 conformity events vs threshold; debate-vs-ensemble divergence trend | Independent-first protocol (P2 baseline before any cross-talk); sealed ballots (P5); heterogeneous model families (Frozen Set); role-locked Bull/Bear | Subtler conformity through shared training data of *all* frontier models — undetectable by family diversity alone |
| 1.2 | **Hallucination** — invented facts, numbers, filings | D2 strip rate; VERIF-01 verification pass | Citation-or-it-didn't-happen (architecture §8.4); claims typed fact/inference/estimate; memo voiding at 30% strip | Plausible-but-wrong *inference* passes verification by design; PMORT catches some, post hoc |
| 1.3 | **Debater capitulation** — Bear agrees with Bull; adversarial value collapses | D3 role violations; Judge concession-honesty scores | Role-locked closing statements; voided debate + re-run (P4); repeat → META-01 escalation | Performative disagreement (going through motions); partially caught by Judge evidence-scoring |
| 1.4 | **Eloquence > evidence** — persuasive rhetoric wins debates | Judge scores vs outcome correlation (D2) | PM sees Moderator summary + Judge scores, never raw transcript (agent-spec §5.1); randomized order, role masking in judging | LLM-judge biases are reduced, not eliminated (research.md §II) |
| 1.5 | **Training-data contamination** — "skill" on historical periods is memory | C3 memorization probes; C4 cross-model disagreement screen | Evidence-class system: E4 banned, E3 capped, gates run on E1 only (backtesting §2, §6) | E1-only validation is slow; pressure to cheat grows with impatience — see 6.2 |
| 1.6 | **Prompt drift / silent regression** — a prompt "improvement" degrades behavior | Believability discontinuity at version tuple boundary (D2); META expected_effect misses | Version-tuple track-record resets (memory §5.2); P11 measured-experiment requirement; rollback plans mandatory | Slow degradations within a version evade discontinuity detection |
| 1.7 | **Model API churn** — provider deprecates/changes a model mid-flight | D6 node failure rates; latency shifts | Abstraction layers (ADR-1/2); version pinning; budgeted migration weeks (implementation-plan risks) | Forced migrations reset believability records by design — a real cost, accepted |
| 1.8 | **Reward hacking by META-01** — optimizing metrics, not outcomes | META proposal hit rate vs fund-level metrics divergence | Frozen Set (configuration §9): cannot touch believability math, gate, breakers, own approval; human approval on every change | Human approver fatigue rubber-stamping — see 6.3 |
| 1.9 | **Context pollution** — memory/lessons anchor instead of inform | D5 anchoring audit | Forced win/loss analog balance; anti-anchoring banner; no retrieval in debate/voting; 40-lesson cap (memory §3.2, §4.2) | Anchoring below audit sensitivity |
| 1.10 | **Correlated blind spots** — all models miss the same thing (shared training corpus) | Stance correlation matrix (D3) catches *expressed* correlation only | Family heterogeneity; quant signals as non-LLM second opinion (Phase 2+) | The deep version is unmitigable with current LLMs: what no model can see, no diversity of models reveals. Accepted (§7) |

## 2. Statistical & Validation Failure Modes

| # | Failure | Detection | Mitigation | Residual |
|---|---|---|---|---|
| 2.1 | **Backtest overfitting** | DSR at true trial count; PBO | Trial Registry (no unregistered backtests); CPCV; admission checklist (backtesting §3) | Registry only counts *our* trials; ideas imported from literature carry the literature's invisible trial count |
| 2.2 | **Look-ahead bias** | D6 nightly audit (threshold: zero, forever) | `as_of`/`available_at` at storage layer; mandatory `as_known_at` API; refusal semantics (ADR-6) | Vendor-side leakage (mislabeled knowledge time upstream) — partially caught by EDGAR spot-audits |
| 2.3 | **Survivorship bias** | universe audit vs delisted counts | Sharadar delisted coverage; delisting-return handling (backtesting §3.1) | — |
| 2.4 | **Selection bias in reporting** — quietly featuring the good runs | Reporting standards: every number carries evidence class + registry N (backtesting §8) | Dashboard renders incomplete results greyed-out | Narrative selection in human conversations about the fund — unmitigable by software |
| 2.5 | **Luck mistaken for skill** | PSR/MinTRL on every record; D1 honesty rails | MinTRL countdown widget; G-gates with explicit non-criteria (validation G1.3b) | Regime luck: a strategy can be "validated" across 2 regimes and still be one big regime bet |
| 2.6 | **Cost-model optimism** | fill-divergence report (monthly) | Conservative model; 1×/2×/3× sensitivity; recalibration trigger; G2.3 | Paper fills themselves are optimistic; true impact unknowable until real capital (accepted) |
| 2.7 | **Signal decay post-admission** | live-vs-backtest fidelity bands (G2.2b KS test) | Re-validation triggers; last_validation_date decay on signal weight (backtesting §3.5) | Decay slower than detection window erodes quietly |

## 3. Market & Portfolio Failure Modes

| # | Failure | Detection | Mitigation | Residual |
|---|---|---|---|---|
| 3.1 | **Hidden concentration** — ten trades, one bet | RISKA portfolio_interactions; factor exposure caps (D1) | Factor model neutralization (Phase 2); sector caps; RISKA's explicit nightmare-brief (agent-spec §6.1) | Phase 1 runs on net-band proxy only — a real gap until the factor model lands |
| 3.2 | **Regime shift** — book built for yesterday's market | MACRO regime label changes; rolling beta/vol (D1) | regime_mismatch haircut (P6); regime-aware lessons; breakers as the backstop | Regime detection lags by construction; breakers bound the damage, not the lag |
| 3.3 | **Crowding** — our "edge" is everyone's edge | SENT crowding anecdotes; QUANT crowding_note | Bear receives correlated-exposure context; crowding flags in memos | Detection is anecdotal at our data tier; positioning data procurement is a Phase 4 question |
| 3.4 | **Liquidity illusion** | ADV participation headroom (D1); abnormal_volume flags | 2% ADV cap; min_adv floor; EXEC participation caps | Liquidity vanishes exactly when needed; caps are calibrated to normal markets |
| 3.5 | **Stop cascades / gap risk** — stops fill far through levels | path stats (MAE) vs stop levels in episodes | Stops are decision-time-declared; intraday monitors at 60s; breakers above stops | Overnight gaps blow through any stop; sizing is the only true defense — hence 5% position cap |
| 3.6 | **Short squeeze** | borrow status; abnormal volume | Easy-to-borrow only; shorts via Phase 2 gate | Even ETB names squeeze; short size caps inherit from position caps |

## 4. Operational & Data Failure Modes

| # | Failure | Detection | Mitigation | Residual |
|---|---|---|---|---|
| 4.1 | **Silent data corruption** | hash-chain verification (D6, daily); vendor revision events | Raw payload archive; rebuild-from-log drills (quarterly) | Corruption *before* our ingestion boundary, within vendor history |
| 4.2 | **Stale data trading** | staleness sentinels; P1 freshness gate | Auto-exclusion of stale names; exit-only fallbacks (api-data §8) | — |
| 4.3 | **Broker/API outage** | heartbeats; order-state timeouts | Fail-closed order manager; IBKR mirror as fallback path; P12 | Mid-order outages leave ambiguous state; reconciliation + exit-only mode is the recovery, not prevention |
| 4.4 | **Loop death (silent)** | watchdog heartbeats (SEV-1) | P12 halt; human-initiated recovery with cooldown | — |
| 4.5 | **Config error** — fat-fingered limit | config hashing; P11 review; gate unit tests | Frozen Set for the dangerous knobs; changes at cycle boundaries only | A *plausible-but-wrong* value passes review; post-hoc P11 retrospective is the catch |
| 4.6 | **Cost blowout** | D4 budget meter; 80% alert | Budget governor degrade policy — structurally cannot silently overspend (architecture §5) | Degrades trade quality for cost; frequent degrades = mis-specified ambition (monitored) |
| 4.7 | **Secret leakage** | — (prevention-only) | Secrets in env/manager only; never in config, prompts, or event log (configuration §10) | LLM provider-side logging of prompt contents is outside our control; no secrets in prompts, ever |

## 5. Organizational / Meta Failure Modes (the human is in the loop — so the human is in the registry)

| # | Failure | Detection | Mitigation | Residual |
|---|---|---|---|---|
| 5.1 | **E1 impatience** — believing a contaminated backtest because waiting is hard | E4 watermarks; evidence class on every number | Banned-from-reports rule; MinTRL countdown as a constant reframe (backtesting §2) | Software can't stop you from believing a watermarked number. Named here because naming helps. |
| 5.2 | **Goalpost moving** — softening a gate mid-evaluation | Amendment log (empty unless P11-before-evaluation) | validation-criteria amendment rule | — |
| 5.3 | **Approval fatigue** — rubber-stamping META proposals | META hit-rate vs approval-rate divergence | P11 measured-experiment requirement makes lazy approvals visible at +4 weeks | A patient adversary (or drift) can still accumulate small approved changes; quarterly review reads them in aggregate |
| 5.4 | **Alert fatigue** | SEV-3 queue depth trend | Severity routing; thresholds tuned *after* baselines (monitoring open item) | — |
| 5.5 | **Dashboard worship** — optimizing metrics over the thing they proxy | Quarterly Validation Report written for a skeptical outsider | Owner-question discipline (every metric names its action); pivot reviews ask the un-gameable question (residual P&L) | Goodhart is forever; rotation of human attention is the only durable defense |
| 5.6 | **Abandonment risk** — solo project stalls; half-built system trades on | Phase scoping: every phase ends with a *running, gated* system | Implementation-plan principle: no phase delivers parts; breakers + fail-closed defaults bound a neglected system | A paper fund left running unattended is safe by construction (fail-closed); but its E1 clock keeps running with stale supervision — quarterly rituals are the floor |

## 6. Incident Response (when detection fires)

1. **SEV-1** → automatic action already taken (P10/P12); human investigates from the event log; recovery via P12 checklist (cause → fix → replay test → signed resume → cooldown).
2. **SEV-2/3** → triage at the cadence in monitoring-metrics; every incident gets an entry: cause, response, and — the important part — *which registry row above failed to predict it.*
3. **New failure mode discovered** → added to this registry with its detection + mitigation before the incident closes. The registry is append-mostly; rows are never deleted, only marked superseded.
4. **Quarterly:** registry read end-to-end against the quarter's incidents; residual-risk column re-assessed.

## 7. Accepted Risks (consciously carried, not mitigated)

- **A1 — Shared-corpus blind spots (1.10):** all frontier LLMs share most of their training distribution; true cognitive diversity is bounded. Carried because quant signals (non-LLM) partially hedge it and nothing else exists.
- **A2 — Paper-fill optimism floor (2.6):** true market impact is unknowable without real capital. Carried with conservative modeling and explicit labeling; resolved only if live capital is ever pursued.
- **A3 — Believability resets on model churn (1.7):** provider deprecations periodically burn track-record history. Carried as the cost of heterogeneity; version-carryover prior (0.5) softens it.
- **A4 — Regime-count poverty (2.5):** even 24 months of E1 may span 2–3 regimes; some regime risk is unvalidatable on any realistic timeline. Carried with breakers as the universal backstop.
- **A5 — Solo-human dependency (5.6):** one person is the approval queue, the quarterly ritual, and the kill switch. Carried by design at this scale; revisit if the project ever has a second pair of eyes.

## 8. Open Items
- Positioning/crowding data source evaluation (Phase 4) → would upgrade 3.3 from anecdotal to measured.
- Chaos-drill calendar (broker outage simulation, vendor-revision storm) → schedule with Phase 2's fire-drills.
- Registry row → automated test mapping: each AUTO-detectable row should eventually have a CI test that proves the detector fires (Phase 2–3 hardening).
