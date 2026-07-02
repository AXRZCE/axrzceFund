# WP4 — Risk gate + order manager + intraday monitor: done-criteria + rulings

**Committed BEFORE implementation code** (operating discipline §1), like WP1's seven, WP2's five,
WP3's seven. **Branch:** `phase1/wp4-risk` (off merged `origin/main` = `a88a8af`, WP3 in).
**R-numbering:** per-WP, restarting at R1 (this is the **WP4 R-series, R1–R7**).

**Binding specs (read against fetched code, not memory):**
`decision-protocols.md` **P7** (risk opinion → code gate; the gate is last and binding; fixed
evaluation order; clamp-vs-reject via `min_clamp_ratio`; gate code errors fail closed) and **P8**
(intraday monitoring, breakers, escalation mini-graph, timeout default-derisk);
`configuration.md` **§6** (the code gate's table), **§7** (drawdown breakers — Frozen-Set §9.3:
levels may only be TIGHTENED by P11), §8 (`escalation_timeout`, `default_derisk_pct`), §1
(`min_adv_usd`, `min_price`);
`agent-specifications.md` §6.1 (RISKA-01 is ADVISORY — the binding gate is code, ADR-4; **the LLM
risk-analyst agent itself is Phase 2** — WP4 builds the gate only, per §7's roster table);
`phase1-completion-plan.md` §WP4 (orders **modeled/logged, never live**, until WP7; limits set from
the actual WP2–WP3 portfolio);
WP0 broker layer: `data/interfaces/alpaca.py` (`AlpacaBroker.submit` is the REAL write path —
G0.5 proved it with real fills; `simulate_fill` models at `_HALF_SPREAD_BPS = 1.0`) + the G0.5
artifacts (`results/g05/`, **n=20 divergence records across two runs: mean_abs 1.94 bps, median
1.07 bps, max +10.4 bps** — recomputed from the committed artifacts);
`graphs/pm.py` (`TradeProposal` + sizing audit = the gate's input; `ASSUMED_ROUND_TRIP_COST_BPS=20`
is the flagged placeholder this WP retires); [wp3-readout.md](wp3-readout.md) carried limitations.

**Goal.** The emotion-free enforcement layer: a **code** risk gate that blocks or clamps any
breaching PM decision; an order manager that turns approved proposals into **modeled, logged,
replay-stamped orders — with ZERO live submissions** (the cardinal rule); an intraday monitor that
fires the §7 breakers on injected breaches; and the **real cost model** replacing WP3's 20 bps
placeholder. RISKA-01/COMP-01 (LLM governance agents) are Phase 2 — out of scope here.

---

## Proposed numeric limits (for Akshar's ratification — derived from evidence, thin spots flagged)

Evidence base: the actual WP3 decision record (PM sizes observed: **0.735%** MDT, **0.5%-capped**
synthetic contested, **no_trade** COST) at `starting_paper_nav = $1M`; the golden-day universe's
measured dollar-ADV (pit_store, ~May 25–Jun 30 window, n=25 days/name); G0.5's measured fill
divergence; config §5/§6 standing values.

| Limit | Proposed value | Evidence / justification (one line) |
|---|---|---|
| `max_position_pct_nav` | **5%** ($50k) — keep §6 | Observed max PM size 0.735% ⇒ ~7× headroom even after adds; no evidence to move it. |
| `max_new_position_pct_nav` | **2.5%** ($25k) — keep §5 | Already binding in `graphs/pm.py` sizing; never approached (max 0.735%). |
| `max_sector_pct_nav` | **20%** gross — keep §6 | ⚠️ THIN (N=2 proposals, both different sectors): binds only at ~8 same-sector starter positions; adopt, exercise at WP6; **re-derived at WP6 close from the real book**. |
| `max_gross` / `net_band` | **150% / ±30%** — keep §6 | ⚠️ THIN (Phase-1 book is 0–2 positions; gross ≈ 1.2% max observed): adopt §6 defaults, first real exercise is WP6's week; **re-derived at WP6 close from the real book**. |
| `max_adv_participation_pct` | **2%** of 20-day ADV — keep §6 | Measured ADV: AVGO ~$8.0B, COST ~$1.1B, MDT ~$493M, LULU ~$340M ⇒ 2% ≥ $6.8M/day vs $50k max position — never binds by ~100–3000×, which is the intended design ("binding liquidity would mean we're simulating a fund we aren't"). |
| `min_adv_usd` (P1 floor, ENFORCED IN THE GATE) | **$20M** — keep §1 | **Evidence finding:** the WP2 fixture names BNC (~$1.0M) and BIOX (~$0.1M) are FAR below the floor — the gate must re-check it so a sub-floor name can never reach the order path even if screening regresses. |
| `min_price` | **$5.00** — keep §1 | Same gate re-check; all observed candidates ≥ ~$180. |
| `min_clamp_ratio` | **0.8** — keep §6 | Behavior pinned by R1's boundary test (trim to ≥80% ⇒ clamp; needing more ⇒ reject). |
| Breakers §7 | **pod −5%/−7.5%; fund −6% (derisk to 75%)/−10% HALT; cooldown 3** — keep | Frozen-Set §9.3 (tighten-only); at $1M NAV the fund trips are −$60k/−$100k; no P&L history yet to justify tightening. ⚠️ THIN by construction — first exercised via R4's injected breaches, then WP6. |
| `escalation_timeout` / `default_derisk_pct` | **10 min / 50%** — keep §8 | Red-tested at R5; no latency evidence yet to move them. |
| **Cost model (NEW — replaces the 20 bps placeholder)** | `round_trip_cost_bps = max(2 × half_spread_bps + impact_bps, 6)` with `half_spread_bps = 2`, `impact_bps = 25 × participation_fraction` | **Measured (G0.5 artifacts, n=20):** modeled-vs-broker divergence mean_abs **1.94 bps**, median **1.07 bps**, **max +10.4 bps**. 2 bps/side ≈ **1.0× the measured mean** (it is ~2× only vs the WP0 model's 1 bp/side floor); the **+10.4 bps outlier is known tail risk** the 6 bps round-trip floor only PARTIALLY covers — accepted for Phase 1, monitored. Impact linear in participation (negligible at our ~1e-4 participation). Floor 6 bps ⇒ the edge gate (3×) demands ≥18 bps edge. ⚠️ Materially LOWER than the 20 bps placeholder (edge bar drops 60→18 bps) — honest number, flagged since it loosens P6. |

---

## Rulings (decided a priori — the bar; no post-hoc redefinition of "pass")

Every ruling names a red test; gut the implementation → red. Standing practice: key guts
demonstrated red-on-gut then restored.

### R1 — The code gate blocks or clamps every breaching decision, fail-closed, in P7's fixed order.
A `TradeProposal` breaching any table limit is **rejected or clamped** before it can become an
order. Evaluation order FIXED per P7.3: universe floors (ADV/price) → position limit → sector cap →
gross/net exposure → ADV participation → breaker state (factor caps are Phase 2 per §6). First
failure rejects with a **machine-readable reason**. **Clamp rule:** the gate may trim size when
`clamped/proposed ≥ min_clamp_ratio (0.8)`; needing a deeper trim ⇒ the proposal was wrong ⇒
reject. **Gate code errors fail closed (reject)** — an exception inside a limit check must never
pass a proposal.
- **Red tests:** a 6%-NAV proposal is rejected (or clamped only if ≥0.8×); gut the gate → the
  breaching order passes → red. Boundary pinned at exactly 0.8 (trim to exactly 80% ⇒ CLAMP).
  A sub-floor name (BNC-class, ADV < $20M) is rejected on the universe floor. An injected exception
  in a check ⇒ reject, not pass.

### R2 — ZERO live submissions: the dry-run wall is CODE with a committed test. *(The cardinal rule.)*
The order path terminates at a **modeled order event** — never at `AlpacaBroker.submit`. Enforced
structurally: the WP4 order manager takes **no broker write handle** (it may read market data /
clock); a `submit`-shaped call in the WP4 path **raises** (`LiveSubmissionBlocked`), and the guard
is not a config flag someone can flip — lifting it is WP7's own logged, reviewed change.
- **Red tests:** an attempted submission through the order path raises, proven by a test with a
  spy broker (its `submit` must NEVER be called — even the paper API counts as live for WP4);
  an AST/source-scan test pins that the order-manager module does not import the broker's submit
  surface; gut the wall → the spy records a submit → red. (G0.5 already proved the write path
  WORKS; WP4 must prove it is never REACHED.)

### R3 — The order manager produces correct, deterministic, replay-stamped modeled orders.
`TradeProposal` → modeled order: side from direction; **qty = floor(NAV × size_pct_nav / price)**
whole shares (rounding rule pinned); order type from `entry_plan` (Phase-1 vocabulary: market_open /
limit); TIF day; modeled fill via the WP0 `simulate_fill` convention at the cost model's half-spread.
Deterministic: same proposal + same market state ⇒ byte-identical order; every order event carries a
ReplayTuple incl. `manifest_version`.
- **Red tests:** a canned order fails — change the proposal (size/direction/ticker) and the order
  must change accordingly (gut the derivation → identical orders → red); the rounding rule pinned
  (e.g. $7,350 at $178.61 ⇒ 41 shares, never 41.15); replay: the order is reconstructable from the
  event log with no broker/LLM access.

### R4 — The intraday monitor fires the §7 breakers on injected breaches; responses are logged actions.
Monitor consumes position marks + NAV; on an **injected** breach it emits the configured response
event: pod −5% ⇒ halve-gross action; pod −7.5% ⇒ flatten action; fund −6% ⇒ derisk-to-75% (+ new
entries ×0.5); fund −10% ⇒ **HALT** (P12 semantics: cancel-working, block approvals, notify);
stop-loss and machine-checkable invalidation triggers fire per trade. Responses are **logged
actions** (no live orders — R2 wall applies to monitor-initiated actions too). Breaker distances
are computed from the high-water mark, emitted every check (the "distance-to-trip" dashboard number).
- **Red tests:** each injected breach produces exactly its configured response event (gut a breaker
  → injected breach yields nothing → red); boundary at exactly −5.0% pinned (trip at ≤ −5.0%, not
  < −5.0% — decide and pin); HALT blocks subsequent approvals in the same session (state check).

### R5 — Escalation timeout ⇒ default de-risk, red-tested.
The P8.4 escalation path is bounded: if an escalation decision does not complete within
`escalation_timeout = 10 min`, the default action fires — **reduce the affected position 50%**
(modeled/logged, R2 wall). Allowed escalation outputs are only `hold | reduce | hedge | exit`;
never new entries, never size increases (Frozen-Set §9.5).
- **Red tests:** an injected never-completing escalation ⇒ the default-derisk action event at
  timeout (gut the timeout → the position hangs unmanaged → red); an escalation output of
  "increase" is rejected as a protocol violation.

### R6 — The real cost model replaces the 20 bps placeholder this WP.
`round_trip_cost_bps(order_notional, adv_usd_20d) = max(2·half_spread_bps + impact_bps, floor)`
with the ratified parameters (table above): half_spread 2 bps (≈1.0× the G0.5 measured mean_abs of
1.94 bps, n=20; the +10.4 bps outlier is known tail risk the floor partially covers),
`impact_bps = 25 × participation_fraction`, floor 6 bps. `graphs/pm.py` consumes it (the flagged
`ASSUMED_ROUND_TRIP_COST_BPS` constant is deleted); the P6 edge check (`expected_edge_bps ≥ 3×
cost`) now runs against the modeled cost of THIS order in THIS name.
- **MANDATORY recalibration checkpoint (committed here as part of this ruling, ratified by Akshar):**
  the cost parameters are **re-derived at WP6 from the dry-run week's logged IEX quotes** (measured
  spreads), and again at WP7 from real paper fills — this is a **WP6 gate item**, not a hope. The
  Phase-1 parameters above are explicitly interim.
- **Red tests:** the model is size- and liquidity-sensitive — a larger order in a thinner name
  costs strictly more (gut to a constant → the monotonicity test red); the floor binds at megacap
  sizes (6 bps, so required edge 18 bps); the placeholder constant is GONE from graphs/pm.py
  (grep-test); pm.py's edge check consumes the model (a proposal failing 3× the modeled cost is
  rejected).

### R7 — Edge-case rulings, pre-committed (the WP0–WP3 pattern: decide now, not mid-incident).
1. **Market closed:** the order manager models fills ONLY against a fresh market state; when the
   clock says closed, orders queue as `pending_next_open` events with no modeled fill (a fill
   modeled off stale prices is a hoax). Red: a closed-clock order gets no fill event.
2. **Partial fills (modeled path):** Phase-1 modeled fills are complete-at-once BY CONSTRUCTION
   (order ≤ 0.005% of ADV makes partials unrealistic to model honestly) — RULED: model complete
   fills, RECORD the rule, and log `filled_qty == qty` explicitly so WP7's real partial-fill
   handling has a defined divergence point. Red: the fill event must carry the full-fill marker.
3. **Stale data for a held name (P1/P8):** a held position whose marks are older than the staleness
   gate flips to **exit-only management** and is flagged to the monitor; new adds blocked. Red: an
   injected stale mark ⇒ exit-only flag + blocked add.
4. **Monitor down mid-session (P12 watchdog):** the monitor emits a heartbeat; a missed-heartbeat
   watchdog (test-injectable clock) escalates to HALT semantics — block approvals until human
   review, per P12's "silent loop" HALT source. Red: an injected heartbeat gap ⇒ HALT event.

---

## Build order (all spend-free until the E2E smoke; LLM spend in WP4 ≈ $0 — the gate/monitor are code)
0. **WP4-OPEN (this doc)** — done-criteria + proposed limits committed; **STOP for Akshar's gate.**
1. Cost model (R6) + pm.py placeholder retirement — pure code.
2. Risk gate (R1) — pure code, table-driven from configuration.md via `param_number`.
3. Order manager + dry-run wall (R2, R3) — modeled orders, spy-broker tests.
4. Intraday monitor + breakers + escalation timeout (R4, R5) — injected-breach tests.
5. Edge cases (R7) + full-suite + gut demos.
6. E2E smoke: replay a stored WP3 proposal (no LLM needed — `reconstruct_decision`) through
   gate → order manager → modeled fill → monitor with an injected breach; artifact + readout.
   *(If a fresh live-LLM cycle is wanted instead, it is ≤ $0.35 per the WP3 smokes — Akshar's call.)*

## Standing rules (unchanged)
Committed re-runnable tests; gut-demos red-then-restored; fixtures/licensed data never committed;
vendor scan before every commit; every artifact ReplayTuple-stamped incl. `manifest_version`;
branch + PR; **the human reads the PR — no self-merge; no step skips its gate.**

**Gate (Akshar).** Ratify (i) the proposed limits table (esp. the cost-model parameters — the edge
bar drops 60→18 bps — and the two ⚠️ THIN adoptions) and (ii) rulings R1–R7, BEFORE any
implementation code. Zero spend this checkpoint.
