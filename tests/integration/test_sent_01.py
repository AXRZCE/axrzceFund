"""SENT-01 — DEFERRED at WP2 (logged ruling: docs/wp2-sent01-defer-ruling.md).

No PIT-correct news source exists for a post-cutoff fixture backtest: pit_store has no news table,
and Alpaca's News API exposes only publisher timestamps (created_at / updated_at), not the fund's
ingestion-time available_at — so a historical decision date has no honest, look-ahead-free stamp.
Shipping a raw-adapter get_news to "pass" would violate R2/R5 and fail the look-ahead audit. Per the
pre-committed done-criteria fallback, SENT-01 defers rather than fake sentiment.

This module is an explicit, visible marker of the deferral (and keeps CI green). It un-skips when a
PIT news source + a SENT-01 golden fixture + lock land — see the ruling for the un-defer condition
and the run_sent_01 / test_sent_01 shape (a TECH-01 clone with for_roles=['SENT-01']).
"""

import pytest

pytest.skip(
    "SENT-01 deferred at WP2 — no PIT-correct news source (see docs/wp2-sent01-defer-ruling.md)",
    allow_module_level=True,
)
