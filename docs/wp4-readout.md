# WP4 readout — Risk gate + order manager + intraday monitor (R1–R7)

**Branch:** `phase1/wp4-risk` → PR to `main` (Akshar's merge gate). **Done-criteria:**
[wp4-done-criteria.md](wp4-done-criteria.md) (committed before code; limits ratified with three
corrections; R6 re-ratified after the degeneracy finding). **Artifact of record:**
`results/wp4/replay_smoke.json` (LLM-free replay — **WP4 total LLM spend: $0.00**).

## Evidence per ruling

| R | What was built | Proof |
|---|---|---|
| **R1** gate | [graphs/risk_gate.py](../graphs/risk_gate.py): P7.3 fixed order (universe floors → position 5% → new 2.5% → sector 20% → gross/net → ADV 2% → breaker state); clamp iff ratio ≥ 0.8 (boundary == 0.8 ⇒ CLAMP, pinned); non-clampable rejects; **any exception ⇒ reject** (poisoned-book test); `$20M`-units guard | 15 tests; smoke: both stored proposals gated with full allowance audit |
| **R2** THE WALL | [graphs/orders.py](../graphs/orders.py): `submit_live` raises **unconditionally** (paper = live); **no broker import** (AST-scanned); spy-broker proves `submit` never reached | 3 tests; the replay smoke runs with no broker object in existence |
| **R3** orders | floor-rounded whole shares (pinned), deterministic, canned-order variation tests, half-spread modeled fills, stamped events (`manifest_version`) | 8 tests; smoke orders: 91 & 62 shares @ 80.151027 modeled fill, `full_fill: true` |
| **R4** monitor | [graphs/monitor.py](../graphs/monitor.py): §7 breakers on injected breaches (pod −5 halve / −7.5 flatten; fund −6 → `derisk` state the gate consumes; −10 → HALT); boundary ≤ −X% exact; HALT never auto-decays; P12 human recovery → 3-session exit-only `cooldown` (gate rejects new entries) | 8 tests incl. **HALT-blocks-gate END-TO-END**; smoke halt demo: inject −10% → `fund_halt` → re-gated proposal rejected `breaker_halt` |
| **R5** escalation | unacknowledged breach ≥ 10 min (fake clock, boundary exact) ⇒ default 50% de-risk; outputs restricted to hold/reduce/hedge/exit | 3 tests |
| **R6** cost model | [core/costs.py](../core/costs.py) **as amended**: `max(2×2 + 50·√p, 4)` — see the amendment story below | 10 tests; smoke shows per-trade costs in the audit |
| **R7** edge cases | market-closed ⇒ `pending_next_open`, no fill, no breaker eval off stale closed marks; complete-fill rule explicit (`full_fill` marker); stale-held-name ⇒ exit-only (gate blocks adds, stale marks decide nothing); watchdog: silent monitor ⇒ HALT end-to-end | 6 tests |

Suite: **290 passed** (WP3 close: 238). Vendor scans clean at every commit.

## The R6 amendment, told honestly

The first-ratified model used **linear** impact (`25 × participation`, floor 6). My own committed
test documented that the floor bound at Phase-1 sizes — and the reviewer surfaced what that
actually meant: the variable region began above ~8% participation while the gate caps at 2%, so
**in the reachable universe the "real model" was a constant**. Akshar ruled it REJECTED (per-trade
variation is the point; degenerate-in-practice doesn't get grandfathered), doc-first. The amended
model uses the **√-impact law** with η **derived from a stated anchor** — model(p = 0.02, the
ADV-cap boundary) ≈ the G0.5 tail (~11 bps) ⇒ η = (11−4)/√0.02 = 49.5 → 50 — and the floor
repositioned to 4 (pure double-spread, a degenerate-input guard that no real trade touches).
In-universe span: 4.5 bps (p=1e-4) → 11.1 bps (p=0.02). Consequence stated plainly: small liquid
trades carry a LOWER edge bar (~13 bps) than the old constant 18; big/thin trades a higher one
(to ~33). Reviewer re-executed the full grid before CP2 proceeded.

## Gut-demo table (every gut red, then restored)

| Gut applied | Red result |
|---|---|
| Gate allowance loop disabled | **6 red** — incl. a 6% order passing untouched |
| Wall's raise neutered | `DID NOT RAISE` |
| Cost → constant (first model) | 3 red |
| √-impact flattened (amended model) | **4 red** — in-universe sensitivity, η-anchor, above-floor, monotonicity |
| Fund-halt breaker disabled | **3 red** — incl. the END-TO-END halt-blocks-gate test |
| Escalation timeout disabled | red (breach hangs unmanaged) |

## The replay smoke (zero LLM — Akshar's smoke ruling)

Stored WP3 proposals replayed through cost → edge → gate → orders → fill → monitor on the
hash-verified `wp3_cp1_20260625` fixture (MDT last close 80.135, fixture ADV $396.4M):

| Case | cost (per-trade) | edge bar | gate | order |
|---|---|---|---|---|
| stored MDT 0.735% | **4.2153 bps** | 12.65 | approved, untouched | buy 91 @ 80.151027 modeled, full_fill |
| synthetic contested 0.5% | **4.1776 bps** | 12.53 | approved, untouched | buy 62 @ 80.151027 modeled |
| HALT demo | — | — | inject fund −10% → `fund_halt` → **re-gated proposal REJECTED `breaker_halt`** | none (halted) |

*Honest delta:* the pre-retune verification quoted 4.1931/4.1592 bps using the pit_store 25-day ADV
(~$493M); the replay's canonical input is the **fixture's own trailing-bars ADV** ($396.4M), giving
4.2153/4.1776. Same model, different ADV window — both inputs are recorded in the artifact.
The stored proposal's 400 bps expected edge clears either bar with ~30× headroom.

## Carried to WP6 (consolidated — gate items, not hopes)

1. **Cost recalibration checkpoint (R6, mandatory):** η + half_spread re-derived from the dry-run
   week's logged IEX quotes; again at WP7 from real paper fills.
2. **Sector/gross/net re-derivation:** the 20%/150%/±30% adoptions were evidence-THIN (0–2
   position book); re-derive at WP6 close from the real book.
3. **Shadow-ensemble budget/sampling decision** (carried from WP3): decide at WP6 open.

## Gate

R1–R7 closed, checkboxes + artifact links in the done-criteria. PR opened for full-branch
verification, then **Akshar's WP4 merge gate**. Not self-merged. WP5 (learning loop + PMORT-01 +
dashboard) opens with its own committed done-criteria before any code.
