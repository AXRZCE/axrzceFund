# README.md — Multi-Agent AI Hedge Fund (US Equities, Paper Trading)

A paper-trading hedge fund run by an organization of AI agents — analysts, adversarial debaters, a portfolio manager, and governance agents — modeled on the *governance* of world-class funds (Bridgewater's believability weighting, Millennium's un-appealable risk breakers, Renaissance's shared-knowledge culture) while exploiting what only software can do: total auditability, forced devil's advocacy, instant post-mortems, and risk rules that cannot be emotionally overridden.

**Core stance (from the research):** LLM agents are research-synthesis and governance engines, not alpha oracles. The system is designed so that if LLM stock-picking alpha fails to materialize (the evidence-based base case), the architecture pivots intact to LLM-governance-over-quant-signals.

**Status:** Phase 0 complete (G0 signed 2026-06-24; G0.1/G0.3/G0.5 proofs committed under `results/`) · Phase 1 in progress — WP0, WP1, WP2 merged to `main`, WP3 next · see phase1-completion-plan.md

---

## Document Index

| # | Document | One sentence | Read when |
|---|---|---|---|
| 1 | **research.md** | The evidence base: world-class fund structures, multi-agent LLM state of the art (with honest failure modes), ranked math/ML breakthroughs, and why validation rigor is the real edge. | First, once, fully |
| 2 | **architecture.md** | Seven-layer topology, LangGraph orchestration, 3-tier heterogeneous LLM strategy, dual cadence (daily deep loop + intraday reflexes), and the enforcement boundary: LLMs reason, code enforces. | Before any design question |
| 3 | **agent-specifications.md** | All 15 agents as fill-in-the-blanks specs — mission, reads/writes, schemas, believability metrics, failure guards, prompt anchors, and what each agent *cannot* do. | Before building any agent |
| 4 | **decision-protocols.md** | The twelve workflows P1–P12 — screening, isolated memos, earned debate, sealed weighted ballots, PM synthesis, the code gate, escalation, learning loop, halts — plus the edge-case ledger. | Before wiring any workflow |
| 5 | **configuration.md** | Every tunable parameter with value and rationale — the fund's bylaws — including the breakers and the human-only Frozen Set. | Whenever a number is needed |
| 6 | **api-data-sources.md** | Brokers (Alpaca paper primary), market data phasing (IEX → Polygon), the Sharadar point-in-time fundamentals decision, EDGAR as ground truth, ingestion rules and budgets. | Phase 0, and at any vendor question |
| 7 | **backtesting-framework.md** | The honesty machinery: evidence classes E1–E4, Trial Registry, CPCV/DSR/PBO/MinTRL, the cost model, LLM-contamination controls, and protocol-level A/B experiments. | Before trusting any number |
| 8 | **memory-systems.md** | Episodic memory, the 40-lesson-cap semantic store with probation/falsification, and the no-write-API believability store — learning with an immune system. | Before Phase 1 build |
| 9 | **implementation-plan.md** | Phases 0–4 with scopes, build sequences, gate shapes, pre-committed pivots, and week-1 actions. Gates, not dates. | To know what to build next |
| 10 | **validation-criteria.md** | The precise gate numbers G0–G4 — falsifiable, dashboard-sourced, unwaivable — plus quantified pivot triggers and the (distant) live-capital bar. | At every gate evaluation |
| 11 | **monitoring-metrics.md** | Six dashboards, alert severities, and review cadences; every metric named with the question it answers and the action its breach triggers. | When building dashboards; weekly thereafter |
| 12 | **failure-modes-mitigation.md** | The consolidated risk registry — 36 failure modes with detection, mitigation, residual risk — including the human's own failure modes and five consciously accepted risks. | Quarterly ritual; after any incident |
| 13 | **glossary.md** | One project-specific definition per term, from DSR to NO-TRADE to Frozen Set. | Whenever a term is ambiguous |

**Phase-1 / WP working docs** (the build record — reference by name):

| Document | One sentence |
|---|---|
| **phase1-completion-plan.md** | The WP2→WP7 plan + current status (WP2 complete, WP3 next). |
| **wp2-readout.md** | WP2 complete: FUND-TECH + TECH-01 proven, SENT-01 deferred; the R1–R5 proofs + spend. |
| **wp2-sent01-defer-ruling.md** | Why SENT-01 ships deferred (no PIT news source; scope + hollowness) and its un-defer condition. |
| **ballot-summary-reconcile-readout.md** | The WP1-R1 reconcile of `ballot_summary` to the P5 four-field shape. |
| **vm-git-wiring.md** | Track A: the VM self-updates before each run and commits its own proof to `results/`; one-time bootstrap. |
| **vm-soak-setup.md** | The always-on VM soak / G0.5 runbook + git wiring. |
| **data-governance.md** | Standing policy: repo is PUBLIC; vendor data never committed; fixtures gitignored + hash-locked; commit-guard; history scrub. |
| **g0-gate-memo-draft.md** | The signed G0 gate memo; Phase-0 evidence (soak/broker proofs now committed under `results/`). |

## Reading Orders

- **New collaborator (or future you):** 1 → 2 → 4 → 3 → 9, then the rest as needed.
- **Starting to code (Claude Code session):** 9 (current phase scope) → 2 (layer being built) → 3/4 (the component's spec/protocol) → 5 (its numbers) → 7 (its tests).
- **Evaluating a gate:** 10, with 11 open beside it.
- **Something went wrong:** 12 (find the row) → 4/P12 (the response) → 11 (the metric).

## Dependency Map (who defers to whom)

```
research.md ──► architecture.md ──► agent-specifications.md ──► decision-protocols.md ──► configuration.md
                     │                                                  │
                     ▼                                                  ▼
              api-data-sources.md ◄──────────────── backtesting-framework.md ──► validation-criteria.md
                     │                                       │
                     ▼                                       ▼
              memory-systems.md ──► implementation-plan.md ──► monitoring-metrics.md
                                                             ──► failure-modes-mitigation.md ──► glossary.md
```
Rule: a conflict between documents is resolved by the upstream document; a conflict within reality is resolved by architecture.md §2's principles.

## Five Rules That Summarize Everything

1. **LLMs reason; code enforces.** No prompt is ever a risk control.
2. **Never read `available_at > decision_ts`.** The look-ahead audit's threshold is zero, forever.
3. **Independent first, debate second, sealed votes always.** Sycophancy is measured, not assumed away.
4. **Every number carries its evidence class.** E4 is banned; only E1 gates agent claims; MinTRL says when a record means anything.
5. **The weights, the gate, the breakers, and the log are incorruptible** — not by humans mid-cycle, not by META-01 ever.

## Working With Claude Code

- Keep the docs in `/docs`; reference them by name in prompts ("build P2 per decision-protocols.md and agent-specifications.md §3.2"). (The set has grown past the original 12 with the Phase-1/WP working docs indexed above.)
- configuration.md is hashed into `config_version` at runtime — treat edits as deployments (P11), not text edits.
- When implementation reveals a doc is wrong, **change the doc first** (P11 for config/protocols; direct edit + note for others pre-Phase-1), then the code. The docs are the spec; drift between them and the code is a bug in one of the two.
- First session: implementation-plan.md → "Immediate Next Actions (Phase 0, week 1)".

---
*Documentation set v1.1 · July 2026 · This is a research/learning project trading paper money; nothing herein is investment advice.*
