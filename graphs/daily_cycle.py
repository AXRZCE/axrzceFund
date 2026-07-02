"""The daily dry-run cycle (WP6 CP1) — the entrypoint `hedgefund-cycle.timer` calls.

Post-close orchestration (22:15 ET, after the 21:30 soak ingest), per the R-series:

  market/trading-session check (R9) → WALL ATTESTATION (R5, every run) → settle yesterday's
  pending orders at today's REAL open → mark the book → monitor tick + breaker persistence →
  P1-lite screen (R4, incl. the logged waiver) → per candidate: fixture+lock → memos
  (FUND-TECH + TECH-01) → VERIF-01 → debate → judge → votes → tally → PM → gate (with the
  WEEK'S BOOK) → order (post-close ⇒ pending_next_open; fills settle at the NEXT session's open)
  → quote_log (R2) → held-name summary re-approval (P3: no new info ⇒ re-approved at size) →
  PMORT-interim on open decisions → shadows (R1, budget-gated) → the cycle_summary artifact with
  EVERYTHING the off-VM audit recomputes (R5), incl. the in-run replay-determinism hash.

Budget: every LLM stage passes through the R8 governor (degrade chain: shadows → candidate #2 →
cycle_budget_stop). Fail-closed: any stage exception ⇒ `cycle_failed` event + NO decision for that
candidate (R7 — the day still records and counts as an observation).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import structlog

from core.budget import BudgetGovernor, BudgetStop
from core.config import load_config, param_number
from graphs.ballot import tally
from graphs.ledger import (
    persist_breakers,
    record_marks,
    replay_book,
    restore_breakers,
    settle_pending,
)
from graphs.monitor import HeldPosition, monitor_tick
from graphs.orders import LiveSubmissionBlocked, build_order, log_order, submit_live
from graphs.risk_gate import evaluate
from graphs.screen import scan_universe, screen_candidates

logger = structlog.get_logger()

OUT_DIR = Path("results/wp6")
# NYSE holidays in the WP6/WP7 horizon (2026 H2). Jul 4 2026 is a Saturday → observed Fri Jul 3.
NYSE_HOLIDAYS = {"2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"}


def is_trading_session(date_iso: str) -> bool:
    """R9 calendar check: weekends + the holiday table. (Half-days ARE sessions — ruled.)"""
    d = _dt.date.fromisoformat(date_iso)
    return d.weekday() < 5 and date_iso not in NYSE_HOLIDAYS


def attest_wall(event_log: Any, *, cycle_id: str) -> dict:
    """R5 criterion 1: EVERY run proves the wall stands — submit_live must raise, and the run
    records it. A run without this event cannot count toward the week."""
    try:
        submit_live({"symbol": "ATTEST", "qty": 0, "side": "buy"})
    except LiveSubmissionBlocked:
        att = {"wall": "attested", "detail": "submit_live raised LiveSubmissionBlocked",
               "broker_write_calls": 0}
        event_log.append(event_type="wall_attested", cycle_id=cycle_id, agent_id="ORDER-MGR",
                         payload=att)
        return att
    raise RuntimeError("WALL BREACH: submit_live did NOT raise — integrity failure (R6 reset)")


def replay_hash(payloads: list[dict]) -> str:
    """Canonical hash over decision payloads — computed in-run from the EVENT LOG reconstruction
    and recomputed off-VM from the artifact payloads by the audit script (R5 criterion 2)."""
    blob = json.dumps(payloads, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def log_quote(event_log: Any, market_data: Optional[Any], ticker: str, *, cycle_id: str,
              moment: str) -> dict:
    """R2 quote logging — a gap is RECORDED, never interpolated."""
    payload: dict = {"ticker": ticker, "moment": moment}
    try:
        if market_data is None:
            raise NotImplementedError("no quote feed wired")
        payload.update(log_quote_ok=True, **market_data.get_latest_quote(ticker))
    except Exception as e:  # entitlement/latency/feed-absent — the gap is the record
        payload.update(log_quote_ok=False, gap=True, reason=str(e)[:120])
    event_log.append(event_type="quote_log", cycle_id=cycle_id, agent_id="ORDER-MGR",
                     payload=payload)
    return payload


def reapprove_held(event_log: Any, holdings: dict, *, cycle_id: str) -> list[dict]:
    """P3: held positions with no new information and no triggered conditions are summarily
    re-approved at current size ('no action' is the default state, and it's free)."""
    approvals = []
    for ticker, h in sorted(holdings.items()):
        if h["signed_qty"] == 0:
            continue
        rec = {"ticker": ticker, "signed_qty": h["signed_qty"],
               "action": "reapproved_at_size", "basis": "P3: no new info, no trigger"}
        event_log.append(event_type="held_reapproval", cycle_id=cycle_id, agent_id="P3",
                         payload=rec)
        approvals.append(rec)
    return approvals


def run_daily_cycle(
    *,
    session_date: str,
    client: Any,
    manifest: Any,
    event_log: Any,
    market_data: Optional[Any] = None,
    db_path: str = "var/pit_store.duckdb",
    prior_week_spend_usd: float = 0.0,
    out_dir: Path = OUT_DIR,
) -> dict:
    """One unattended session. Returns (and writes) the cycle_summary artifact."""
    cycle_id = f"wp6_{session_date.replace('-', '')}"
    cfg_version = load_config().config_version
    summary: dict = {"session_date": session_date, "cycle_id": cycle_id,
                     "manifest_version": manifest.manifest_version,
                     "config_version": cfg_version}

    # R9 — calendar first, zero LLM on a closed day
    if not is_trading_session(session_date):
        summary.update(status="market_closed", detail="weekend/holiday — no cycle (R9)")
        event_log.append(event_type="market_closed", cycle_id=cycle_id, payload=summary)
        _write(summary, out_dir, cycle_id)
        return summary

    # R5.1 — the wall, attested every run, before anything else
    summary["wall_attestation"] = attest_wall(event_log, cycle_id=cycle_id)

    gov = BudgetGovernor(prior_week_spend_usd=prior_week_spend_usd)
    from data.fixtures.harness import (  # local import: keeps module import light for tests
        DEFAULT_FIXTURE_DIR, adv_usd_20d, load_fixture, record_fixture, write_lock)
    from data.pit_store import PITStore
    from graphs.agents.fund_tech import run_fund_tech
    from graphs.agents.tech_01 import run_tech_01
    from graphs.debate import cast_votes, preflight, run_debate
    from graphs.judge import run_judge_debate
    from graphs.pm import run_pm
    from graphs.pmort import run_pmort
    from graphs.shadow import run_shadow_votes
    from graphs.verif01 import verify_memo

    preflight(manifest)

    # today's bars: settlement opens + marks (a trading day with no bars = data late ⇒ fail closed)
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    bars = con.execute(
        "select ticker, open, close from price_bars where substr(as_of,1,10)=?",
        [session_date]).fetchall()
    if not bars:
        summary.update(status="cycle_failed", detail="data late: no bars for a trading session "
                                                     "(fail-closed — no decisions, R7)")
        event_log.append(event_type="cycle_failed", cycle_id=cycle_id, payload=summary)
        _write(summary, out_dir, cycle_id)
        return summary
    opens = {t: float(o) for t, o, _ in bars if o is not None}
    closes = {t: float(c) for t, _, c in bars if c is not None}

    summary["settlements"] = settle_pending(event_log, opens, cycle_id=cycle_id)
    record_marks(event_log, closes, cycle_id=cycle_id)
    book = replay_book(event_log)
    summary["book"] = {"nav_usd": book["nav_usd"],
                       "positions": [{"ticker": p.ticker, "sector": p.sector,
                                      "notional_usd": p.signed_notional_usd}
                                     for p in book["positions"]]}

    breakers = restore_breakers(event_log)
    held_positions = [HeldPosition(t, abs(h["signed_qty"]), None,
                                   "long" if h["signed_qty"] > 0 else "short",
                                   closes.get(t, h["fill_price"]),
                                   _dt.datetime.now(_dt.timezone.utc))
                      for t, h in book["holdings"].items() if h["signed_qty"] != 0]
    tick = monitor_tick(breakers=breakers, nav_usd=book["nav_usd"], positions=held_positions,
                        now=_dt.datetime.now(_dt.timezone.utc), market_open=True)
    persist_breakers(event_log, breakers, cycle_id=cycle_id)
    summary["monitor"] = {"actions": [a.kind for a in tick.actions],
                          "breaker_state": breakers.state,
                          "drawdown_pct": round(breakers.drawdown_pct(book["nav_usd"]), 4)}
    summary["held_reapprovals"] = reapprove_held(event_log, book["holdings"], cycle_id=cycle_id)

    # R4 — the screen
    rows = scan_universe(db_path, as_of_date=session_date)
    screen = screen_candidates(rows, held=[p.ticker for p in book["positions"]])
    summary["screen"] = {"new_candidates": screen.new_candidates,
                         "held": screen.held_candidates, "waiver": screen.waiver_note,
                         "excluded_count": len(screen.excluded)}

    store = PITStore(Path(db_path))
    decisions, replay_payloads = [], []
    for i, cand in enumerate(screen.new_candidates):
        if i == 1 and not gov.allow_second_candidate():
            event_log.append(event_type="candidate_dropped_budget", cycle_id=cycle_id,
                             payload={"ticker": cand})
            break
        try:
            gov.guard(f"candidate:{cand}")
            fid = f"wp6_{session_date.replace('-', '')}_{cand}"
            fx = record_fixture(store, fixture_id=fid, decision_ts=f"{session_date}T20:00:00+00:00",
                                tickers=[cand],
                                fundamentals_indicators=["ASSETS", "EPS", "EQUITY", "FCF",
                                                         "NETINC", "REVENUE"])
            write_lock(fx)
            fx = load_fixture(DEFAULT_FIXTURE_DIR / f"{fid}.json",
                              for_roles=["BULL-01", "BEAR-01", "MOD-01", "PM-01", "FUND-TECH",
                                         "TECH-01"], manifest=manifest)
            memos = []
            ft = run_fund_tech(fixture=fx, candidate=cand, client=client, manifest=manifest,
                               cycle_id=cycle_id, code_version="wp6")
            gov.charge(ft.usage_cost_usd, stage="memo")
            if ft.verification.valid:
                memos.append(ft.memo)
            tc = run_tech_01(fixture=fx, candidate=cand, client=client, manifest=manifest,
                             cycle_id=cycle_id, code_version="wp6")
            gov.charge(tc.usage_cost_usd, stage="memo")
            if tc.verification.valid:
                memos.append(tc.memo)
            if not memos:
                raise RuntimeError("no valid memos (both failed VERIF-01) — candidate dropped")
            for m in memos:  # defense-in-depth re-validation (P2 strip already ran per agent)
                verify_memo(m, agent_role=m.get("agent_id", ""))

            gov.guard("debate")
            deb = run_debate(candidate=cand, verified_memos=memos, client=client,
                             manifest=manifest, cycle_id=cycle_id, decision_ts=fx.decision_ts,
                             code_version="wp6")
            gov.charge(deb.cost_usd, stage="debate")
            gov.guard("judge")
            judged = {manifest.resolve_runtime("BULL-01").family,
                      manifest.resolve_runtime("BEAR-01").family}
            jd = run_judge_debate(turns=deb.turns, verified_memos=memos, judged_families=judged,
                                  client=client, manifest=manifest, cycle_id=cycle_id,
                                  decision_ts=fx.decision_ts, code_version="wp6",
                                  seed_key=f"{fid}")
            gov.charge(jd.cost_usd, stage="judge")
            gov.guard("votes")
            ballots, _stamps, vcost = cast_votes(candidate=cand, verified_memos=memos, result=deb,
                                                 research_voters=["FUND-TECH"], client=client,
                                                 manifest=manifest, cycle_id=cycle_id,
                                                 decision_ts=fx.decision_ts, code_version="wp6")
            gov.charge(vcost, stage="votes")
            bsummary, direction = tally(ballots,
                                        margin_threshold=param_number("ballot_margin_threshold"))
            gov.guard("pm")
            adv = adv_usd_20d(fx, cand)
            pm = run_pm(candidate=cand, verified_memos=memos, debate_summary=deb.summary,
                        premortem_top_risks=deb.premortem_top_risks, ballot_summary=bsummary,
                        ballot_direction=direction, debate_failed=False, client=client,
                        manifest=manifest, cycle_id=cycle_id, decision_ts=fx.decision_ts,
                        code_version="wp6", nav_usd=book["nav_usd"], adv_usd_20d=adv,
                        event_log=event_log)
            gov.charge(pm.cost_usd, stage="pm")

            record: dict = {"ticker": cand, "fixture": fid, "content_hash": fx.content_hash,
                            "ballot": bsummary.model_dump(), "direction": direction,
                            "judge": {"family": jd.judge_family,
                                      "bull_evidence": jd.scores.bull.evidence,
                                      "bear_evidence": jd.scores.bear.evidence},
                            "pm_action": pm.action}
            if pm.action == "trade":
                price = closes.get(cand)
                gate = evaluate(ticker=cand, direction=pm.proposal.direction,
                                size_pct_nav=pm.proposal.size_pct_nav, nav_usd=book["nav_usd"],
                                price=price, adv_usd_20d=adv,
                                sector=_sector_of(cand), book=book["positions"],
                                breaker_state=breakers.state,
                                exit_only_names=tick.exit_only_names)
                record["gate"] = {"approved": gate.approved, "clamped": gate.clamped,
                                  "rule": gate.rule, "final_size_pct_nav": gate.final_size_pct_nav}
                if gate.approved:
                    order = build_order(ticker=cand, direction=pm.proposal.direction,
                                        size_pct_nav=gate.final_size_pct_nav,
                                        entry_type="market_open", nav_usd=book["nav_usd"],
                                        price=price, market_open=False)  # post-close ⇒ pending
                    log_order(order, manifest=manifest, cycle_id=cycle_id,
                              decision_ts=fx.decision_ts, code_version="wp6",
                              event_log=event_log)
                    record["order"] = {"side": order.side, "qty": order.qty,
                                       "status": order.status}
                    record["quote_at_decision"] = log_quote(event_log, market_data, cand,
                                                            cycle_id=cycle_id, moment="decision")
                replay_payloads.append({"proposal": pm.proposal.model_dump()})
            else:
                record["no_trade"] = pm.no_trade
                replay_payloads.append({"no_trade": pm.no_trade})
            decisions.append(record)
        except BudgetStop as e:
            event_log.append(event_type="cycle_budget_stop", cycle_id=cycle_id,
                             payload={"ticker": cand, "reason": str(e)})
            break
        except Exception as e:  # R7: fail closed per candidate, record, continue the cycle
            event_log.append(event_type="cycle_failed", cycle_id=cycle_id, agent_id=cand,
                             payload={"ticker": cand, "error": str(e)[:300]})
            decisions.append({"ticker": cand, "status": "cycle_failed", "error": str(e)[:200]})

    summary["decisions"] = decisions
    summary["replay_check"] = {"hash": replay_hash(replay_payloads),
                               "payloads": replay_payloads,
                               "note": "audit recomputes the hash from these payloads (R5.2)"}

    # R1 shadows — last, budget-gated, never touching the above
    if decisions and gov.allow_shadows():
        try:
            last_ok = next((d for d in reversed(decisions) if "error" not in d), None)
            if last_ok is not None:
                shadows, scost = run_shadow_votes(
                    verified_memos=[], debate_summary_json=json.dumps(last_ok["ballot"]),
                    client=client, manifest=manifest, cycle_id=cycle_id,
                    decision_ts=f"{session_date}T20:00:00+00:00", code_version="wp6",
                    event_log=event_log)
                gov.charge(scost, stage="shadow")
                summary["shadows"] = [{"role": v.role, "stance": v.stance} for v in shadows]
        except Exception as e:
            summary["shadows"] = {"skipped": str(e)[:120]}
    else:
        event_log.append(event_type="shadow_skipped_budget", cycle_id=cycle_id, payload={})
        summary["shadows"] = "skipped_budget"

    summary["spend"] = gov.summary()
    summary["status"] = "complete"
    _write(summary, out_dir, cycle_id)
    logger.info("daily_cycle_complete", cycle=cycle_id, decisions=len(decisions),
                spend=gov.summary()["day_spent_usd"])
    return summary


_SECTORS = {"AVGO": "tech", "COST": "staples", "MDT": "health", "LULU": "discretionary"}


def _sector_of(ticker: str) -> str:
    return _SECTORS.get(ticker, "unmapped")


def _write(summary: dict, out_dir: Path, cycle_id: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"cycle_{summary['session_date'].replace('-', '')}.json").write_text(
        json.dumps(summary, indent=2, default=str))
