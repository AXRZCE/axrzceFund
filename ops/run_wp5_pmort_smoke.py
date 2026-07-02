#!/usr/bin/env python
"""WP5 CP2 PMORT smoke — two REAL interim post-mortems on stored decisions. PAID, ≤$2 cap.

(a) INTERIM post-mortem on the stored MDT trade (results/wp3_cp3 + the WP4 modeled entry
    80.151027 of 2026-06-25) against REAL backfilled marks (SEP, through 2026-07-01) — interim:true,
    window_days recorded, no generalizable lesson (schema-enforced; not prompted for either).
(b) The R6a COST no_trade record: counterfactual marks for the DECLINED contested-short over the
    same window + the stored what_would_reopen, captured as the ruled Phase-1-lite episode.

Both run through the REAL capture path (event log, stamps incl. manifest_version); the derived
store is then rebuilt and checked byte-equal WITH the new events. The seat that actually served
(role/model/family, resolved at call time from decided_family=google) is recorded in the artifact.
Marks come from the pit_store — never interpolated; if a window has no vendor bar, the day is
simply absent (recorded as-is).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv(".env")

from core.episodic import Outcome, pending_post_mortems, rebuild_episodic_store  # noqa: E402
from core.event_log import EventLog  # noqa: E402
from core.llm import OpenRouterClient  # noqa: E402
from core.manifest import load_manifest  # noqa: E402
from graphs.pmort import resolve_pmort_seat, run_pmort  # noqa: E402

HARD_CAP = 2.0
PRIOR_CUMULATIVE = 4.41  # WP3 total (~$4.41); WP4 $0.00 (docs/wp4-readout.md)
OUT = Path("results/wp5")
ENTRY_MDT = 80.151027            # the WP4 modeled fill (results/wp4/replay_smoke.json)
ENTRY_DATE = "2026-06-25"
COST_DECISION_DATE = "2026-06-26"


def _marks(ticker: str, after: str) -> list[tuple[str, float]]:
    c = duckdb.connect("var/pit_store.duckdb", read_only=True)
    return c.execute(
        "select substr(as_of,1,10) d, close from price_bars where ticker = ? "
        "and substr(as_of,1,10) > ? order by 1", [ticker, after]).fetchall()


def _close_on(ticker: str, day: str) -> float:
    c = duckdb.connect("var/pit_store.duckdb", read_only=True)
    row = c.execute("select close from price_bars where ticker = ? and substr(as_of,1,10) = ?",
                    [ticker, day]).fetchone()
    if row is None:
        raise ValueError(f"no vendor bar for {ticker} on {day} — never interpolate")
    return float(row[0])


def main() -> None:
    man = load_manifest()
    client = OpenRouterClient()
    el = EventLog(Path("var/wp5_smoke_event_log.db"))
    stored_trade = json.loads(Path("results/wp3_cp3/pm_smoke.json").read_text())
    stored_notrade = json.loads(Path("results/wp3_cp4/full_smoke.json").read_text())
    spent = 0.0

    # ── (a) MDT interim: real marks vs the modeled entry ────────────────────────────
    mdt_marks = _marks("MDT", ENTRY_DATE)
    assert mdt_marks, "backfill must have landed real MDT marks (never fabricate)"
    closes = [m for _, m in mdt_marks]
    last = closes[-1]
    pnl = (last - ENTRY_MDT) / ENTRY_MDT * 1e4          # long
    mae = (min(closes) - ENTRY_MDT) / ENTRY_MDT * 1e4
    mfe = (max(closes) - ENTRY_MDT) / ENTRY_MDT * 1e4
    proposal = stored_trade["pm_decision"]["proposal"]
    seat = resolve_pmort_seat("google", man)

    r_mdt = run_pmort(
        trade_id="wp5_mdt_interim", ticker="MDT", sector="health", direction="long",
        decision_record={"proposal": proposal, "ballot": stored_trade["ballot"],
                         "modeled_entry": {"fill": ENTRY_MDT, "date": ENTRY_DATE, "qty": 91}},
        outcome=Outcome(pnl_bps=round(pnl, 2), holding_days=len(mdt_marks),
                        exit_reason="interim_mark", mae_bps=round(mae, 2), mfe_bps=round(mfe, 2)),
        premortem_top_risks=proposal.get("premortem_top_risks", []),
        decision_record_ref="results/wp3_cp3/pm_smoke.json + results/wp4/replay_smoke.json",
        interim=True, window_days=len(mdt_marks), decided_family="google",
        client=client, manifest=man, cycle_id="wp5_smoke_mdt",
        decision_ts="2026-07-01T20:00:00+00:00", code_version="wp5-cp2-smoke", event_log=el,
        tags=["interim", "wp3_decision"])
    spent += r_mdt.cost_usd
    assert spent < HARD_CAP

    # ── (b) COST no_trade: counterfactual for the DECLINED contested short (R6a) ─────
    cf_entry = _close_on("COST", COST_DECISION_DATE)
    cost_marks = _marks("COST", COST_DECISION_DATE)
    assert cost_marks, "backfill must have landed real COST marks"
    cf_last = cost_marks[-1][1]
    # sign convention (recorded): counterfactual SHORT P&L — positive when the price FELL
    cf_pnl = (cf_entry - cf_last) / cf_entry * 1e4
    nt = stored_notrade["pm_decision"]["no_trade"]

    r_cost = run_pmort(
        trade_id="wp5_cost_notrade", ticker="COST", sector="staples", direction="no_trade",
        decision_record={"no_trade": nt, "ballot": stored_notrade["ballot"],
                         "counterfactual": {"declined_direction": "short",
                                            "entry_close": cf_entry, "date": COST_DECISION_DATE}},
        outcome=Outcome(pnl_bps=round(cf_pnl, 2), holding_days=len(cost_marks),
                        exit_reason="no_trade",
                        mae_bps=round(min(0.0, (cf_entry - max(m for _, m in cost_marks))
                                      / cf_entry * 1e4), 2),
                        mfe_bps=round(max(0.0, (cf_entry - min(m for _, m in cost_marks))
                                      / cf_entry * 1e4), 2)),
        premortem_top_risks=[fs["scenario"] for fs in
                             stored_notrade["transcript"]["mod_summary"]["premortem"]["failure_scenarios"]]
        if "transcript" in stored_notrade else [],
        decision_record_ref="results/wp3_cp4/full_smoke.json",
        interim=True, window_days=len(cost_marks), decided_family="google",
        client=client, manifest=man, cycle_id="wp5_smoke_cost",
        decision_ts="2026-07-01T20:00:00+00:00", code_version="wp5-cp2-smoke", event_log=el,
        tags=["no_trade", "counterfactual", "wp3_decision"])
    spent += r_cost.cost_usd
    assert spent < HARD_CAP

    # ── rebuild byte-equal WITH the new events ───────────────────────────────────────
    p = Path("var/wp5_smoke_store.json")
    first = rebuild_episodic_store(el, p)
    second = rebuild_episodic_store(el, p)
    assert first == second, "rebuild must be byte-equal with the smoke events included"

    artifact = {
        "mode": "PMORT smoke (2 real T3 calls)",
        "backfill": {
            "path": "ingest_sep(tickers=['MDT','COST','AVGO','LULU'], window_days=10) — the WP2-A1 passthrough",
            "before": "25 bars/ticker, 2026-06-03..2026-06-24",
            "after": "31 bars/ticker through 2026-07-01 (32 rows added)",
            "interim_window_used": {"MDT": [d for d, _ in mdt_marks],
                                    "COST": [d for d, _ in cost_marks]},
        },
        "seat_served": {"role": seat.role, "model_version": seat.model_version,
                        "family": seat.family, "resolved_from": "decided_family=google at call time"},
        "mdt_interim": {
            "status": r_mdt.status,
            "outcome": {"entry": ENTRY_MDT, "last_mark": last, "pnl_bps": round(pnl, 2),
                        "mae_bps": round(mae, 2), "mfe_bps": round(mfe, 2),
                        "window_days": len(mdt_marks), "stop_71_50_breached": min(closes) <= 71.50},
            "post_mortem": r_mdt.post_mortem.model_dump() if r_mdt.post_mortem else None,
            "stamp": r_mdt.stamp,
        },
        "cost_notrade": {
            "status": r_cost.status,
            "counterfactual": {"declined_direction": "short", "entry_close": cf_entry,
                               "last_mark": cf_last, "counterfactual_short_pnl_bps": round(cf_pnl, 2),
                               "sign_convention": "positive = the declined short would have profited",
                               "what_would_reopen": nt.get("what_would_reopen")},
            "post_mortem": r_cost.post_mortem.model_dump() if r_cost.post_mortem else None,
            "stamp": r_cost.stamp,
        },
        "pending_queue_after": [p["trade_id"] for p in pending_post_mortems(el)],
        "rebuild_byte_equal_with_new_events": True,
        "manifest_version": man.manifest_version,
        "spend": {"smoke_usd": round(spent, 6), "cap_usd": HARD_CAP,
                  "cumulative_ledger_usd": round(PRIOR_CUMULATIVE + spent, 4)},
    }
    blob = json.dumps(artifact)
    from ops.precommit_guard import is_vendor_data
    assert is_vendor_data("results/wp5/pmort_smoke.json", blob.encode()) is None

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pmort_smoke.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({
        "seat": artifact["seat_served"],
        "mdt": {"status": r_mdt.status, "pnl_bps": round(pnl, 2),
                "verdict": r_mdt.post_mortem.outcome_vs_thesis if r_mdt.post_mortem else None,
                "process": r_mdt.post_mortem.process_grade if r_mdt.post_mortem else None,
                "outcome_grade": r_mdt.post_mortem.outcome_grade if r_mdt.post_mortem else None},
        "cost": {"status": r_cost.status, "cf_short_pnl_bps": round(cf_pnl, 2),
                 "verdict": r_cost.post_mortem.outcome_vs_thesis if r_cost.post_mortem else None},
        "spend": artifact["spend"],
    }, indent=2))


if __name__ == "__main__":
    main()
