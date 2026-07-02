#!/usr/bin/env python
"""WP4 E2E replay smoke — ZERO LLM calls, zero spend (Akshar's smoke ruling: replay, not live).

Replays the STORED WP3 proposals (the committed results/wp3_cp3/pm_smoke.json artifact — the
0.735% MDT trade and the 0.5%-capped synthetic contested case) through the WP4 chain:

    per-trade cost model (R6 as amended) → edge re-check → risk gate (R1) → order manager (R3)
    → modeled fill (behind THE WALL, R2) → monitor tick (R4)

plus an injected fund −10% HALT to show the monitor→gate integration END-TO-END (the re-gated
proposal is rejected). Price/ADV come from the local golden-day fixture (hash-verified against the
committed lock). Artifact: results/wp4/replay_smoke.json with ReplayTuple stamps (manifest_version).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.costs import round_trip_cost_bps
from core.config import param_number
from core.event_log import EventLog
from core.manifest import load_manifest
from data.fixtures.harness import DEFAULT_FIXTURE_DIR, adv_usd_20d, load_fixture
from graphs.monitor import BreakerStateMachine, HeldPosition, monitor_tick
from graphs.orders import build_order, log_order
from graphs.pm import check_edge
from graphs.risk_gate import evaluate

FIXTURE_ID = "wp3_cp1_20260625"
NAV = 1_000_000.0
OUT = Path("results/wp4")
NOW = datetime(2026, 6, 25, 20, 0, tzinfo=timezone.utc)  # the fixture's decision boundary


def _last_close(fx, ticker: str) -> float:
    bars = sorted((b for b in fx.payload["price_bars"] if b["ticker"] == ticker),
                  key=lambda b: str(b.get("as_of", "")))
    return float(bars[-1]["close"])


def main() -> None:
    man = load_manifest()
    stored = json.loads(Path("results/wp3_cp3/pm_smoke.json").read_text())
    proposal = stored["pm_decision"]["proposal"]          # the 0.735% MDT trade, replay source
    contested_size = stored["contested_demo_synthetic"]["sizing_audit"]["size_pct_nav"]  # 0.5

    fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{FIXTURE_ID}.json",
                      for_roles=["PM-01"], manifest=man)
    lock = json.loads(Path(f"data/fixtures/locks/{FIXTURE_ID}.lock.json").read_text())
    assert fx.content_hash == lock["content_hash"], "fixture hash != committed lock"
    price = _last_close(fx, "MDT")
    adv = adv_usd_20d(fx, "MDT")
    el = EventLog(Path("var/wp4_replay_event_log.db"))
    mult = param_number("edge_to_cost_multiple")

    cases = []
    for label, size, edge in (("stored_mdt_proposal", float(proposal["size_pct_nav"]),
                               float(proposal["expected_edge_bps"])),
                              ("synthetic_contested_capped", float(contested_size),
                               float(proposal["expected_edge_bps"]))):
        notional = NAV * size / 100.0
        cost = round_trip_cost_bps(notional, adv)
        check_edge(edge, cost)  # raises if the stored edge no longer clears the per-trade bar
        gate = evaluate(ticker="MDT", direction=proposal["direction"], size_pct_nav=size,
                        nav_usd=NAV, price=price, adv_usd_20d=adv, sector="health",
                        book=[], breaker_state="normal")
        assert gate.approved, f"{label}: gate rejected a clean stored proposal: {gate.reason}"
        order = build_order(ticker="MDT", direction=proposal["direction"],
                            size_pct_nav=gate.final_size_pct_nav,
                            entry_type=proposal["entry_plan"]["type"], nav_usd=NAV,
                            price=price, market_open=True)
        stamp = log_order(order, manifest=man, cycle_id=f"wp4_replay_{label}",
                          decision_ts=fx.decision_ts, code_version="wp4-cp2-smoke",
                          event_log=el)
        # monitor tick with the new position held, healthy marks — no actions expected
        b = BreakerStateMachine(NAV)
        held = [HeldPosition("MDT", order.qty, stop_price=None,
                             direction=proposal["direction"], last_mark=price, mark_at=NOW)]
        tick = monitor_tick(breakers=b, nav_usd=NAV, positions=held, now=NOW, market_open=True)
        cases.append({
            "label": label, "size_pct_nav": size,
            "cost_bps": round(cost, 4), "edge_bar_bps": round(mult * cost, 4),
            "stored_expected_edge_bps": edge, "edge_check": "PASS",
            "gate": {"approved": gate.approved, "clamped": gate.clamped, "rule": gate.rule,
                     "final_size_pct_nav": gate.final_size_pct_nav,
                     "allowances": gate.audit["allowances_pct_nav"]},
            "order": {"symbol": order.symbol, "side": order.side, "qty": order.qty,
                      "notional_usd": order.notional_usd, "status": order.status,
                      "modeled_fill_price": order.modeled_fill_price,
                      "full_fill": order.full_fill},
            "monitor_tick_actions": [a.kind for a in tick.actions],
            "replay_stamp": stamp,
        })

    # END-TO-END HALT: inject fund −10% → the monitor flips state → the SAME proposal is rejected
    b = BreakerStateMachine(NAV)
    halt_actions = b.tick(900_000.0)
    regated = evaluate(ticker="MDT", direction=proposal["direction"],
                       size_pct_nav=float(proposal["size_pct_nav"]), nav_usd=900_000.0,
                       price=price, adv_usd_20d=adv, sector="health", book=[],
                       breaker_state=b.state)
    assert not regated.approved and regated.rule == "breaker_halt"

    artifact = {
        "mode": "LLM_FREE_REPLAY (zero spend)",
        "replay_source": "results/wp3_cp3/pm_smoke.json (committed WP3 artifact)",
        "fixture_id": FIXTURE_ID, "fixture_hash_verified": True,
        "content_hash": fx.content_hash, "manifest_version": man.manifest_version,
        "market_inputs": {"price_last_close": price, "adv_usd_20d": round(adv, 2)},
        "cases": cases,
        "halt_end_to_end_demo": {
            "injected": "NAV 1,000,000 → 900,000 (fund −10.0%)",
            "monitor_actions": [a.kind for a in halt_actions],
            "breaker_state": b.state,
            "regated_proposal": {"approved": regated.approved, "rule": regated.rule},
        },
        "wall": "no broker object exists anywhere in this run — modeled orders only (R2)",
    }
    blob = json.dumps(artifact)
    from ops.precommit_guard import is_vendor_data
    assert is_vendor_data("results/wp4/replay_smoke.json", blob.encode()) is None

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "replay_smoke.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({"cases": [{k: c[k] for k in ("label", "cost_bps", "edge_bar_bps",
                                                   "gate", "order")} for c in cases],
                      "halt_demo": artifact["halt_end_to_end_demo"]}, indent=2))


if __name__ == "__main__":
    main()
