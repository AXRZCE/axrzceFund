"""P1-lite candidate screen (WP6 R4) — the screen implementable NOW, deterministic, zero LLM.

    SP500 (point-in-time) ∩ fundamentals-covered (≥6 ARQ indicators) ∩ ADV20 ≥ $20M ∩ price ≥ $5
    → ranked by 20-day dollar-ADV (descending, ticker tiebreak) → top-N NEW candidates
    + ALL held positions (P1.3: re-underwriting is mandatory, never optional).

Deferred screens recorded per the R4 ruling: event screen (no PIT news source — SENT-01 deferred),
quant screen (no signal registry — Phase 2). The pure ranking core (`screen_candidates`) takes
plain rows so determinism and floor-exclusion are unit-testable without the store; `scan_universe`
is the thin pit_store adapter (integration-tested where the store exists).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import structlog

from core.config import param_number

logger = structlog.get_logger()

MIN_ADV_USD = param_number("min_adv_usd") * 1e6      # $20M ($20M parses as 20 — the WP4 units guard)
MIN_PRICE_USD = param_number("min_price")            # 5.00
MIN_FUND_INDICATORS = 6                              # the CP1a coverage bar (all 6 ARQ indicators)
WEEK_NEW_CANDIDATE_CAP = 2                           # R4: week-scoped operational cap (config allows 10)


@dataclass(frozen=True)
class ScreenRow:
    ticker: str
    in_sp500: bool
    n_fund_indicators: int
    adv_usd_20d: float
    last_close: float


@dataclass(frozen=True)
class ScreenResult:
    new_candidates: list[str]        # top-N by dollar-ADV
    held_candidates: list[str]       # every held name (mandatory re-underwriting)
    excluded: dict[str, str]         # ticker -> first exclusion reason (auditable)
    waiver_note: str                 # the R4 min_memos waiver, logged EVERY cycle


def screen_candidates(
    rows: Iterable[ScreenRow],
    held: Iterable[str],
    *,
    top_n: int = WEEK_NEW_CANDIDATE_CAP,
) -> ScreenResult:
    """Pure, deterministic: same rows ⇒ same result. Held names bypass the ranking (they are
    candidates by P1.3) but NOT the universe floors — a held name failing floors is surfaced via
    the monitor's exit-only path, not silently re-underwritten here."""
    held_set = set(held)
    eligible: list[ScreenRow] = []
    excluded: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: r.ticker):
        if not r.in_sp500:
            excluded[r.ticker] = "not_sp500_pit"
        elif r.n_fund_indicators < MIN_FUND_INDICATORS:
            excluded[r.ticker] = f"fundamentals_coverage<{MIN_FUND_INDICATORS}"
        elif r.adv_usd_20d < MIN_ADV_USD:
            excluded[r.ticker] = "below_adv_floor"
        elif r.last_close < MIN_PRICE_USD:
            excluded[r.ticker] = "below_price_floor"
        else:
            eligible.append(r)

    ranked = sorted(eligible, key=lambda r: (-r.adv_usd_20d, r.ticker))
    new_candidates = [r.ticker for r in ranked if r.ticker not in held_set][:top_n]
    result = ScreenResult(
        new_candidates=new_candidates,
        held_candidates=sorted(held_set),
        excluded=excluded,
        waiver_note=("WP6 R4 waiver active: 2-memo cycle (FUND-TECH + TECH-01); "
                     "min_memos_required=3 waived by ruling — SENT-01 deferred (logged), "
                     "MACRO/QUANT are Phase 2."),
    )
    logger.info("screen_complete", new=new_candidates, held=result.held_candidates,
                eligible=len(eligible), excluded=len(excluded))
    return result


def scan_universe(db_path: str = "var/pit_store.duckdb",
                  as_of_date: Optional[str] = None) -> list[ScreenRow]:
    """Thin pit_store adapter: one deterministic SQL scan producing ScreenRows as of the latest
    (or given) date. Read-only."""
    import duckdb

    c = duckdb.connect(db_path, read_only=True)
    boundary = as_of_date or c.execute(
        "select max(substr(as_of,1,10)) from price_bars").fetchone()[0]
    q = """
    with px as (
        select ticker,
               avg(close * volume) as adv,
               max_by(close, as_of) as last_close
        from price_bars
        where substr(as_of,1,10) <= ?
          and substr(as_of,1,10) > CAST(CAST(? AS DATE) - INTERVAL 40 DAY AS VARCHAR)
        group by ticker
    ),
    fund as (
        select ticker, count(distinct indicator) as ni from fundamentals
        where substr(available_at,1,10) <= ? group by ticker
    ),
    spx as (
        select ticker, max_by(in_index, as_of) as in_idx from universe_membership
        where index_name = 'SP500' and substr(available_at,1,10) <= ? group by ticker
    )
    select px.ticker, coalesce(spx.in_idx, false), coalesce(fund.ni, 0), px.adv, px.last_close
    from px left join fund using (ticker) left join spx using (ticker)
    """
    rows = c.execute(q, [boundary, boundary, boundary, boundary]).fetchall()
    c.close()  # same-process PITStore opens (read-write) need the file released
    return [ScreenRow(ticker=t, in_sp500=bool(s), n_fund_indicators=int(n),
                      adv_usd_20d=float(a or 0.0), last_close=float(p or 0.0))
            for t, s, n, a, p in rows]
