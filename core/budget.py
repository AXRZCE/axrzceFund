"""Daily spend governor (WP6 R8) — $1.50/day hard, week ≤$10, the WP3 degrade pattern in code.

Degrade chain, IN ORDER (ruled): drop shadows → drop candidate #2 → `cycle_budget_stop` (no
further LLM calls that day). Never a silent overage: every charge is recorded; the stop emits an
event via the caller. Evidence base: ~$0.35/candidate full-chain (CP4), PMORT ~$0.01, shadows
≤$0.03; R1's shadow stop is $0.10/day.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

DAILY_CAP_USD = 1.50
WEEK_CAP_USD = 10.0
SHADOW_DAY_BUDGET_USD = 0.10       # R1
CANDIDATE_COST_ENVELOPE_USD = 0.45  # full chain + headroom (evidence ~$0.35)
SHADOW_COST_ENVELOPE_USD = 0.05


class BudgetStop(Exception):
    """The daily/week cap is reached — no further LLM calls (fail-closed, never silent)."""


@dataclass
class BudgetGovernor:
    prior_week_spend_usd: float = 0.0
    day_spent_usd: float = 0.0
    shadow_spent_usd: float = 0.0
    stopped: bool = False
    degrade_log: list = field(default_factory=list)

    def charge(self, cost_usd: float, *, stage: str) -> None:
        """Record a real cost. Crossing a cap STOPS the day (the caller emits cycle_budget_stop)."""
        self.day_spent_usd += cost_usd
        if stage == "shadow":
            self.shadow_spent_usd += cost_usd
        if (self.day_spent_usd >= DAILY_CAP_USD
                or self.prior_week_spend_usd + self.day_spent_usd >= WEEK_CAP_USD):
            self.stopped = True
            self.degrade_log.append(f"STOP at ${self.day_spent_usd:.4f} after {stage}")
            logger.warning("cycle_budget_stop", day=round(self.day_spent_usd, 4), stage=stage)

    def guard(self, stage: str) -> None:
        """Called BEFORE any LLM stage: once stopped, nothing else runs today."""
        if self.stopped:
            raise BudgetStop(f"budget stop active — {stage} skipped (R8)")

    # ── the degrade chain, in ruled order ────────────────────────────────────────
    def allow_shadows(self) -> bool:
        """First to go: shadows dropped when the shadow budget or headroom is gone."""
        ok = (not self.stopped
              and self.shadow_spent_usd < SHADOW_DAY_BUDGET_USD
              and self.day_spent_usd + SHADOW_COST_ENVELOPE_USD <= DAILY_CAP_USD)
        if not ok:
            self.degrade_log.append("shadows dropped")
        return ok

    def allow_second_candidate(self) -> bool:
        """Second to go: candidate #2 dropped when its envelope no longer fits under the cap."""
        ok = (not self.stopped
              and self.day_spent_usd + CANDIDATE_COST_ENVELOPE_USD <= DAILY_CAP_USD)
        if not ok:
            self.degrade_log.append("candidate #2 dropped")
        return ok

    def summary(self) -> dict:
        return {"day_spent_usd": round(self.day_spent_usd, 6),
                "shadow_spent_usd": round(self.shadow_spent_usd, 6),
                "daily_cap_usd": DAILY_CAP_USD, "week_cap_usd": WEEK_CAP_USD,
                "prior_week_spend_usd": round(self.prior_week_spend_usd, 6),
                "stopped": self.stopped, "degrade_log": list(self.degrade_log)}
