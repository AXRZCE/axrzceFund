"""WP6 CP1 red tests — screen, ledger/breaker persistence, budget chain, audit, attestation.
Pure code + tmp event logs; zero LLM, zero store dependency (the scan adapter is integration-only).

Gut map: screen sort dropped → determinism red; floor check dropped → sub-floor red; breaker
restore dropped → persistence red; allow_second_candidate gutted → chain red; audit hash-compare
gutted → doctored artifact passes → red; attest_wall event dropped → audit criterion red.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from core.budget import (
    CANDIDATE_COST_ENVELOPE_USD,
    DAILY_CAP_USD,
    BudgetGovernor,
    BudgetStop,
)
from core.event_log import EventLog
from graphs.daily_cycle import attest_wall, is_trading_session, replay_hash
from graphs.ledger import (
    config_doc_carries_starting_nav,
    persist_breakers,
    record_marks,
    replay_book,
    restore_breakers,
    settle_pending,
)
from graphs.monitor import BreakerStateMachine
from graphs.screen import MIN_ADV_USD, ScreenRow, screen_candidates
from ops.audit_week import audit_range, audit_session


def _row(t, adv=100e6, close=100.0, sp=True, ni=6):
    return ScreenRow(ticker=t, in_sp500=sp, n_fund_indicators=ni, adv_usd_20d=adv, last_close=close)


# ── R4: the screen ─────────────────────────────────────────────────────────────────
def test_screen_deterministic_same_rows_same_result():
    rows = [_row("B", adv=50e6), _row("A", adv=90e6), _row("C", adv=70e6)]
    r1 = screen_candidates(rows, held=[])
    r2 = screen_candidates(list(reversed(rows)), held=[])  # input order must not matter
    assert r1 == r2
    assert r1.new_candidates == ["A", "C"]  # top-2 by dollar-ADV


def test_screen_excludes_every_floor():
    rows = [_row("OK"), _row("BNC", adv=1.0e6), _row("PENNY", close=4.99),
            _row("NOTSPX", sp=False), _row("THINFUND", ni=4)]
    r = screen_candidates(rows, held=[])
    assert r.new_candidates == ["OK"]
    assert r.excluded == {"BNC": "below_adv_floor", "PENNY": "below_price_floor",
                          "NOTSPX": "not_sp500_pit",
                          "THINFUND": "fundamentals_coverage<6"}
    assert MIN_ADV_USD == 20e6


def test_held_names_are_always_candidates_but_never_double_count():
    rows = [_row("A", adv=90e6), _row("H", adv=95e6)]
    r = screen_candidates(rows, held=["H"])
    assert r.held_candidates == ["H"]
    assert r.new_candidates == ["A"]  # H is held — not consuming a NEW slot


def test_waiver_logged_every_cycle():
    assert "min_memos_required=3 waived" in screen_candidates([], held=[]).waiver_note


# ── ledger: book replay + settlement + breaker persistence ─────────────────────────
def _order_event(el, symbol, side, qty, status, fill=None, ref="t1", sector="tech"):
    el.append(event_type="modeled_order", cycle_id="c", agent_id="ORDER-MGR",
              payload={"order": {"symbol": symbol, "side": side, "qty": qty,
                                 "order_type": "market_open", "tif": "day", "limit_price": None,
                                 "notional_usd": qty * 100.0, "status": status,
                                 "modeled_fill_price": fill, "full_fill": fill is not None},
                       "sector": sector, "replay_tuple": {"trade_id": ref}})


def test_book_replays_fills_marks_and_nav(tmp_path):
    el = EventLog(tmp_path / "e.db")
    _order_event(el, "MDT", "buy", 91, "modeled_filled", fill=80.151027)
    record_marks(el, {"MDT": 79.20}, cycle_id="c")
    book = replay_book(el)
    assert [p.ticker for p in book["positions"]] == ["MDT"]
    assert abs(book["nav_usd"] - (1_000_000 + 91 * (79.20 - 80.151027))) < 0.01


def test_pending_settles_at_next_open_never_without_a_bar(tmp_path):
    el = EventLog(tmp_path / "e.db")
    _order_event(el, "MDT", "buy", 91, "pending_next_open", ref="p1")
    _order_event(el, "COST", "sell", 5, "pending_next_open", ref="p2")
    settled = settle_pending(el, {"MDT": 80.00}, cycle_id="c2")  # no COST bar
    assert len(settled) == 1
    assert settled[0]["modeled_fill_price"] == round(80.00 * (1 + 2.0 / 1e4), 6)  # buy fills UP
    book = replay_book(el)
    assert [p["symbol"] for p in book["pending"]] == ["COST"]  # the gap stays pending
    gaps = [e for e in el.get_events() if e.event_type == "settlement_gap"]
    assert gaps and gaps[0].payload["symbol"] == "COST"       # and is RECORDED


def test_settlement_is_idempotent_across_replays(tmp_path):
    el = EventLog(tmp_path / "e.db")
    _order_event(el, "MDT", "buy", 91, "pending_next_open", ref="p1")
    settle_pending(el, {"MDT": 80.0}, cycle_id="c2")
    assert settle_pending(el, {"MDT": 81.0}, cycle_id="c3") == []  # already settled — no double fill


def test_breaker_state_survives_restart_halt_persists(tmp_path):
    el = EventLog(tmp_path / "e.db")
    m = BreakerStateMachine(1_000_000)
    m.tick(900_000.0)                      # → HALT
    persist_breakers(el, m, cycle_id="c")
    el2 = EventLog(tmp_path / "e.db")      # "restart"
    m2 = restore_breakers(el2)
    assert m2.state == "halt" and m2.hwm_usd == 1_000_000  # P12: HALT persists across restarts


def test_starting_nav_doc_literal_guard():
    assert config_doc_carries_starting_nav()


# ── R8: the budget chain, in order ─────────────────────────────────────────────────
def test_degrade_chain_shadows_then_candidate2_then_stop():
    gov = BudgetGovernor()
    gov.charge(0.80, stage="candidate")           # expected day
    assert gov.allow_shadows() and gov.allow_second_candidate()
    gov.charge(0.30, stage="candidate")           # 1.10 — candidate #2 envelope (0.45) no longer fits
    assert not gov.allow_second_candidate()       # 2nd degrade step
    assert gov.allow_shadows()                    # shadows still fit (1.10 + 0.05 <= 1.50)
    gov.charge(0.08, stage="shadow")
    gov.charge(0.03, stage="shadow")              # shadow budget (0.10) exhausted
    assert not gov.allow_shadows()                # 1st degrade step (by budget)
    gov.charge(0.35, stage="pm")                  # 1.56 >= 1.50 → STOP
    assert gov.stopped
    with pytest.raises(BudgetStop):
        gov.guard("anything")                     # 3rd step: nothing else runs today


def test_week_cap_stops_even_under_daily_cap():
    gov = BudgetGovernor(prior_week_spend_usd=9.60)
    gov.charge(0.45, stage="candidate")           # 10.05 >= 10 week cap
    assert gov.stopped


def test_candidate_envelope_matches_evidence():
    assert CANDIDATE_COST_ENVELOPE_USD == 0.45 and DAILY_CAP_USD == 1.50


# ── R5/R9: attestation, calendar, replay hash, the audit ──────────────────────────
def test_wall_attestation_event_written(tmp_path):
    el = EventLog(tmp_path / "e.db")
    att = attest_wall(el, cycle_id="c")
    assert att["wall"] == "attested" and att["broker_write_calls"] == 0
    assert [e for e in el.get_events() if e.event_type == "wall_attested"]


def test_trading_calendar_july_2026():
    assert not is_trading_session("2026-07-03")   # observed Independence Day (Jul 4 = Saturday)
    assert not is_trading_session("2026-07-04")   # Saturday
    for d in ("2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"):
        assert is_trading_session(d)              # the clean target week


def _fake_artifact(tmp_path, date_iso, **over):
    a = {"session_date": date_iso, "status": "complete",
         "wall_attestation": {"wall": "attested", "broker_write_calls": 0},
         "replay_check": {"payloads": [{"proposal": {"ticker": "MDT", "size_pct_nav": 0.735}}],
                          "hash": replay_hash([{"proposal": {"ticker": "MDT",
                                                             "size_pct_nav": 0.735}}])},
         "spend": {"day_spent_usd": 0.81, "stopped": False},
         "monitor": {"actions": [], "breaker_state": "normal"},
         "decisions": [{"ticker": "MDT"}]}
    a.update(over)
    (tmp_path / f"cycle_{date_iso.replace('-', '')}.json").write_text(json.dumps(a))
    return a


def test_audit_passes_a_clean_session(tmp_path, monkeypatch):
    import ops.audit_week as aw
    monkeypatch.setattr(aw, "ART_DIR", tmp_path)
    _fake_artifact(tmp_path, "2026-07-06")
    r = audit_session("2026-07-06")
    assert r["ok"] and all(r["checks"].values())


def test_audit_catches_a_doctored_artifact(tmp_path, monkeypatch):
    """R5 red test: flip one decision value after the hash was recorded — the audit recomputes
    and FAILS. Gut the hash comparison → the doctored artifact passes → red."""
    import ops.audit_week as aw
    monkeypatch.setattr(aw, "ART_DIR", tmp_path)
    a = _fake_artifact(tmp_path, "2026-07-06")
    a["replay_check"]["payloads"][0]["proposal"]["size_pct_nav"] = 5.0  # doctored AFTER hashing
    (tmp_path / "cycle_20260706.json").write_text(json.dumps(a))
    r = audit_session("2026-07-06")
    assert not r["ok"] and r["checks"]["replay_determinism"] is False


def test_audit_missing_attestation_fails(tmp_path, monkeypatch):
    import ops.audit_week as aw
    monkeypatch.setattr(aw, "ART_DIR", tmp_path)
    _fake_artifact(tmp_path, "2026-07-06", wall_attestation={})
    assert audit_session("2026-07-06")["ok"] is False


def test_audit_classifies_the_week_r6_r7_r9(tmp_path, monkeypatch):
    """One fail-closed day counts as an observation (R7); one miss extends not resets (R6);
    weekend/holiday are non-sessions (R9)."""
    import ops.audit_week as aw
    monkeypatch.setattr(aw, "ART_DIR", tmp_path)
    _fake_artifact(tmp_path, "2026-07-06")
    _fake_artifact(tmp_path, "2026-07-07", status="cycle_failed", detail="LLM outage")
    _fake_artifact(tmp_path, "2026-07-08")
    _fake_artifact(tmp_path, "2026-07-09")
    # 07-10 missing → MISSED (1 miss: week extends, not resets)
    r = audit_range("2026-07-03", "2026-07-10")
    classes = {d["date"]: d["class"] for d in r["days"]}
    assert classes["2026-07-03"] == "non_session" and classes["2026-07-04"] == "non_session"
    assert classes["2026-07-07"] == "fail_closed_observation"
    assert r["missed"] == ["2026-07-10"]
    assert r["week_ok"] is True            # 1 miss, no integrity failures
    # a second miss resets
    (tmp_path / "cycle_20260708.json").unlink()
    r2 = audit_range("2026-07-03", "2026-07-10")
    assert r2["week_ok"] is False and len(r2["missed"]) == 2


# ── the 2026-07-03 deploy-checkpoint catch: mixed-config DuckDB opens in one process ─


def test_session_bars_releases_the_store_for_read_write(tmp_path):
    """THE supervised-cycle failure shape: after the read-only bars read, a READ-WRITE open of the
    same file (PITStore) must succeed in the same process. Gut _session_bars' close → DuckDB's
    mixed-config ConnectionException → red."""
    import duckdb

    from graphs.daily_cycle import _session_bars

    db = tmp_path / "store.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create table price_bars(ticker varchar, as_of varchar, open double, close double)")
    con.execute("insert into price_bars values ('MDT', '2026-07-02T00:00:00', 80.0, 79.5)")
    con.close()

    bars = _session_bars(str(db), "2026-07-02")
    assert bars == [("MDT", 80.0, 79.5)]
    rw = duckdb.connect(str(db))          # read-write open MUST succeed now
    rw.execute("insert into price_bars values ('MU', '2026-07-02T00:00:00', 1000.0, 1010.0)")
    rw.close()
