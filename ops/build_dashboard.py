#!/usr/bin/env python
"""Dashboard v1 (WP5 R5) — a $0 static generator over the REAL committed decision records.

Reads the ACTUAL results/ artifacts — the WP3 pipeline smokes + the CP1 seat comparison, the WP4
replay smoke (gate audits, modeled orders, HALT demo, per-trade costs), the WP5 post-mortems +
pending-queue state — plus each artifact's own spend block for the cumulative ledger.

**No sample-data path exists anywhere:** a missing artifact raises (the build FAILS — never a
placeholder render). Every number shown is read from an artifact; tests/test_dashboard.py asserts
rendered spot-values == artifact values and that deleting an artifact breaks the build.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ARTIFACTS = {
    "wp3_seat": Path("results/wp3_cp1/run3/comparison.json"),
    "wp3_debate": Path("results/wp3_cp2/debate_smoke.json"),
    "wp3_pm": Path("results/wp3_cp3/pm_smoke.json"),
    "wp3_full": Path("results/wp3_cp4/full_smoke.json"),
    "wp4_replay": Path("results/wp4/replay_smoke.json"),
    "wp5_pmort": Path("results/wp5/pmort_smoke.json"),
}
OUT_DIR = Path("results/dashboard")


def load_artifacts() -> dict:
    """Fail-closed: a missing artifact FAILS the build (R5 — no placeholder render, ever)."""
    data = {}
    for key, path in ARTIFACTS.items():
        if not path.exists():
            raise FileNotFoundError(
                f"dashboard artifact missing: {path} — the dashboard renders REAL records only; "
                f"a missing record fails the build (WP5 R5)")
        data[key] = json.loads(path.read_text())
    return data


def _e(v) -> str:
    return html.escape(str(v))


def render(data: dict) -> str:
    seat = data["wp3_seat"]
    debate = data["wp3_debate"]
    pm = data["wp3_pm"]
    full = data["wp3_full"]
    wp4 = data["wp4_replay"]
    wp5 = data["wp5_pmort"]

    glm = seat["per_model"]["BULL-01-CAND-GLM"]
    west = seat["per_model"]["BULL-01-BASELINE-WEST"]

    rows_decisions = ""
    for label, art, cand in (("WP3-CP2 debate", debate, debate["candidate"]),
                             ("WP3-CP3 PM cycle", pm, pm["candidate"]),
                             ("WP3-CP4 full pipeline", full, full["candidate"])):
        bs = art["ballot_summary"] if "ballot_summary" in art else art["ballot"]["summary"]
        pmd = art.get("pm_decision") or {}
        action = pmd.get("action", "— (no PM stage)")
        size = (pmd.get("proposal") or {}).get("size_pct_nav", "—")
        rows_decisions += (
            f"<tr><td>{_e(label)}</td><td>{_e(cand)}</td>"
            f"<td>{_e(bs['weighted_score'])}</td><td>{_e(bs['margin'])}</td>"
            f"<td>{'CONTESTED' if bs['contested'] else 'clear'}</td>"
            f"<td>{_e(action)}</td><td>{_e(size)}</td></tr>")

    rows_orders = ""
    for c in wp4["cases"]:
        o = c["order"]
        rows_orders += (
            f"<tr><td>{_e(c['label'])}</td><td>{_e(c['cost_bps'])}</td>"
            f"<td>{_e(c['edge_bar_bps'])}</td><td>{_e(c['gate']['rule'])}</td>"
            f"<td>{_e(o['side'])} {_e(o['qty'])} {_e(o['symbol'])}</td>"
            f"<td>{_e(o['modeled_fill_price'])}</td><td>{_e(o['status'])}</td></tr>")

    halt = wp4["halt_end_to_end_demo"]
    mdt5 = wp5["mdt_interim"]
    cost5 = wp5["cost_notrade"]

    ledger_rows = ""
    ledger = [
        ("WP3 CP1 seat comparison (run3, record)", seat["total_cost_usd"]),
        ("WP3 CP2 debate smoke (recorded)", debate["spend"]["smoke_recorded_usd"]),
        ("WP3 CP3 PM smoke", pm["spend"]["smoke_usd"]),
        ("WP3 CP4 full smoke (recorded)", full["spend"]["smoke_recorded_usd"]),
        ("WP4 (LLM-free replay)", 0.0),
        ("WP5 PMORT smoke", wp5["spend"]["smoke_usd"]),
    ]
    for label, usd in ledger:
        ledger_rows += f"<tr><td>{_e(label)}</td><td>${usd:.4f}</td></tr>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>axrzceFund — decision record v1</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#111}}
table{{border-collapse:collapse;margin:0.8rem 0}}td,th{{border:1px solid #bbb;padding:4px 10px;font-size:14px}}
th{{background:#eee}}h2{{margin-top:1.6rem}}.k{{color:#666;font-size:13px}}</style></head><body>
<h1>axrzceFund — decision record (dashboard v1)</h1>
<p class="k">Every value on this page is read from a committed results/ artifact. A missing artifact fails the build; no sample data exists.</p>

<h2>BULL seat (WP3 R1 — run of record)</h2>
<table><tr><th>model</th><th>mean_composite</th><th>schema_valid_rate</th><th>verdict</th></tr>
<tr><td>z-ai/glm-5.2 (seated)</td><td>{_e(glm['mean_composite'])}</td><td>{_e(glm['schema_valid_rate'])}</td>
<td>{_e(seat['verdict']['outcome'])}</td></tr>
<tr><td>gemini-3.1-pro (baseline)</td><td>{_e(west['mean_composite'])}</td><td>{_e(west['schema_valid_rate'])}</td><td>baseline</td></tr></table>

<h2>Decisions (WP3 smokes)</h2>
<table><tr><th>cycle</th><th>candidate</th><th>weighted_score</th><th>margin</th><th>ballot</th><th>PM action</th><th>size %NAV</th></tr>
{rows_decisions}</table>
<p class="k">WP3-CP4 shadow decorrelation: stance-agreement {_e(full['shadow']['decorrelation']['stance_agreement_rate'])}
over {_e(full['shadow']['decorrelation']['n_pairs'])} pairs. Judge: {_e(full['judge']['family'])} (disjoint from {_e(full['judge']['judged_families'])}).</p>

<h2>Gate → orders (WP4 replay, per-trade costs)</h2>
<table><tr><th>case</th><th>cost bps</th><th>edge bar</th><th>gate rule</th><th>order</th><th>modeled fill</th><th>status</th></tr>
{rows_orders}</table>
<p class="k">HALT end-to-end: {_e(halt['injected'])} → actions {_e(halt['monitor_actions'])} → breaker
state <b>{_e(halt['breaker_state'])}</b> → re-gated proposal rule <b>{_e(halt['regated_proposal']['rule'])}</b>.</p>

<h2>Post-mortems (WP5 — interim)</h2>
<table><tr><th>record</th><th>verdict</th><th>process</th><th>outcome</th><th>pnl bps</th><th>window</th></tr>
<tr><td>MDT trade (interim)</td><td>{_e(mdt5['post_mortem']['outcome_vs_thesis'])}</td>
<td>{_e(mdt5['post_mortem']['process_grade'])}</td><td>{_e(mdt5['post_mortem']['outcome_grade'])}</td>
<td>{_e(mdt5['outcome']['pnl_bps'])}</td><td>{_e(mdt5['outcome']['window_days'])} sessions</td></tr>
<tr><td>COST no_trade (counterfactual short)</td><td>{_e(cost5['post_mortem']['outcome_vs_thesis'])}</td>
<td>{_e(cost5['post_mortem']['process_grade'])}</td><td>{_e(cost5['post_mortem']['outcome_grade'])}</td>
<td>{_e(cost5['counterfactual']['counterfactual_short_pnl_bps'])}</td><td>—</td></tr></table>
<p class="k">Pending post-mortem queue: {_e(wp5['pending_queue_after'] or 'empty')}.
Lessons are capture-only; believability weighting is Phase 3 (no weights exist anywhere).</p>

<h2>Spend ledger (recorded, per artifact; discards documented in the readouts)</h2>
<table><tr><th>item</th><th>USD</th></tr>{ledger_rows}
<tr><th>cumulative (incl. estimated discards)</th><th>${wp5['spend']['cumulative_ledger_usd']:.4f}</th></tr></table>
<p class="k">manifest_version at WP5 smoke: {_e(wp5['manifest_version'])}.</p>
</body></html>"""


def main() -> None:
    data = load_artifacts()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "index.html"
    out.write_text(render(data), encoding="utf-8")
    print(f"dashboard built -> {out}")


if __name__ == "__main__":
    main()
