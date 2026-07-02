"""Intraday monitor (WP4 R4/R5/R7) — §7 breakers, escalation timeout, staleness, watchdog.

All responses are LOGGED ACTIONS (the R2 wall applies: the monitor never submits anything).
Every clock is INJECTED (`now` parameters) — no wall-clock reads, so every path is red-testable
with a fake clock.

**Breaker state machine (config §7, drawdowns from the high-water mark, positive magnitudes):**
  - pod −5% (`pod_halve_dd`)  ⇒ action `pod_halve_gross` (Phase 1: the whole book is one pod);
  - pod −7.5% (`pod_halt_dd`) ⇒ action `pod_flatten`;
  - fund −6% (`fund_derisk_dd`) ⇒ state → `derisk` (the gate consumes it: new-entry ×0.5 policy);
  - fund −10% (`fund_halt_dd`) ⇒ state → `halt` (P12: no approvals until HUMAN recovery);
  boundary pinned: a breaker trips at ≤ −threshold exactly. `halt` NEVER auto-decays —
  `human_recover()` (P12) moves it to `cooldown` (exit-only) for `cooldown_cycles = 3` clean
  sessions, then `normal`. `derisk` decays to `normal` after the drawdown recovers above the
  threshold for 3 consecutive clean sessions.

**Escalation (P8.4 / R5):** an unacknowledged breach older than `escalation_timeout = 10 min`
fires the default action — reduce the affected position 50% (`default_derisk_pct`, config §8;
the literal is parser-shadowed by the escalation_timeout line, so it lives here guarded by a
doc-literal test). Escalation outputs may only be hold/reduce/hedge/exit — never entries/increases.

**Staleness (R7.3):** a held name whose mark is older than the staleness threshold flips to
EXIT-ONLY (adds blocked at the gate via `exit_only_names`; exits remain allowed).

**Watchdog (R7.4 / P12):** the monitor failing silent is itself a breach — a missed heartbeat
beyond the max gap escalates to HALT semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog

from core.config import param_number

logger = structlog.get_logger()

POD_HALVE_DD_PCT = param_number("pod_halve_dd")        # 5.0  (−5% from HWM)
POD_HALT_DD_PCT = param_number("pod_halt_dd")          # 7.5
FUND_DERISK_DD_PCT = param_number("fund_derisk_dd")    # 6.0
FUND_HALT_DD_PCT = param_number("fund_halt_dd")        # 10.0
COOLDOWN_SESSIONS = int(param_number("cooldown_cycles"))       # 3
ESCALATION_TIMEOUT_MIN = param_number("escalation_timeout")    # 10
# config §8 writes `default_derisk_pct = 50%` inside the escalation_timeout line — parser-shadowed,
# so the value lives here; tests/test_monitor.py guards the doc literal.
DEFAULT_DERISK_PCT = 50.0
STALE_MARK_MAX_MIN = 15.0  # a held name's mark older than this ⇒ exit-only (P1 staleness, intraday)

ALLOWED_ESCALATION_ACTIONS = ("hold", "reduce", "hedge", "exit")


def config_doc_carries_default_derisk() -> bool:
    raw = Path("docs/configuration.md").read_text(encoding="utf-8")
    return "`default_derisk_pct = 50%`" in raw


@dataclass
class MonitorAction:
    kind: str          # pod_halve_gross | pod_flatten | fund_derisk | fund_halt | escalation_default_derisk | stop_exit | stale_exit_only | watchdog_halt | tick_skipped_market_closed
    detail: str
    ticker: Optional[str] = None


class BreakerStateMachine:
    """§7 drawdown breakers. Phase 1 treats the whole book as one pod, so the pod and fund
    breakers watch the same NAV series; their ACTIONS differ."""

    def __init__(self, hwm_usd: float):
        if hwm_usd <= 0:
            raise ValueError("hwm must be positive")
        self.hwm_usd = hwm_usd
        self.state = "normal"          # normal | derisk | halt | cooldown
        self._clean_sessions = 0
        self._fired: set[str] = set()  # one action per breaker level per drawdown episode

    def drawdown_pct(self, nav_usd: float) -> float:
        return 100.0 * (self.hwm_usd - nav_usd) / self.hwm_usd

    def tick(self, nav_usd: float) -> list[MonitorAction]:
        """One monitoring check. Emits breaker actions; mutates state. Boundary: ≤ −X% trips."""
        actions: list[MonitorAction] = []
        if nav_usd > self.hwm_usd:
            self.hwm_usd = nav_usd
            self._fired.clear()
        dd = self.drawdown_pct(nav_usd)

        if self.state == "halt":
            return actions  # frozen until human_recover() (P12)

        if dd >= FUND_HALT_DD_PCT:
            self.state = "halt"
            actions.append(MonitorAction("fund_halt",
                           f"fund dd {dd:.2f}% ≥ {FUND_HALT_DD_PCT}%: HALT — cancel working, "
                           f"block approvals, notify human (P12)"))
            return actions
        if dd >= FUND_DERISK_DD_PCT and self.state != "derisk":
            self.state = "derisk"
            self._clean_sessions = 0
            actions.append(MonitorAction("fund_derisk",
                           f"fund dd {dd:.2f}% ≥ {FUND_DERISK_DD_PCT}%: gross → 75%, "
                           f"new entries ×0.5 (gate consumes breaker_state)"))
        if dd >= POD_HALT_DD_PCT and "pod_halt" not in self._fired:
            self._fired.add("pod_halt")
            actions.append(MonitorAction("pod_flatten",
                           f"pod dd {dd:.2f}% ≥ {POD_HALT_DD_PCT}%: flatten pod, no new entries"))
        elif dd >= POD_HALVE_DD_PCT and "pod_halve" not in self._fired:
            self._fired.add("pod_halve")
            actions.append(MonitorAction("pod_halve_gross",
                           f"pod dd {dd:.2f}% ≥ {POD_HALVE_DD_PCT}%: pod gross halved"))

        # decay: derisk/cooldown → normal after clean sessions
        if self.state in ("derisk", "cooldown"):
            if dd < FUND_DERISK_DD_PCT:
                self._clean_sessions += 1
                if self._clean_sessions >= COOLDOWN_SESSIONS:
                    self.state = "normal"
                    self._fired.clear()
            else:
                self._clean_sessions = 0
        return actions

    def human_recover(self) -> None:
        """P12: recovery is ALWAYS human-initiated; re-entry goes through exit-only cooldown."""
        if self.state != "halt":
            raise ValueError("human_recover() only applies from HALT")
        self.state = "cooldown"
        self._clean_sessions = 0

    # ── WP6 R-persistence: breaker state survives process restarts via event-log snapshots ──
    def snapshot(self) -> dict:
        return {"state": self.state, "hwm_usd": self.hwm_usd,
                "clean_sessions": self._clean_sessions, "fired": sorted(self._fired)}

    @classmethod
    def from_snapshot(cls, snap: dict) -> "BreakerStateMachine":
        m = cls(float(snap["hwm_usd"]))
        m.state = snap["state"]
        m._clean_sessions = int(snap.get("clean_sessions", 0))
        m._fired = set(snap.get("fired", []))
        return m


@dataclass
class Escalation:
    """P8.4: a breach awaiting an escalation decision, bounded by the timeout (injected clock)."""

    ticker: str
    created_at: datetime
    acknowledged: bool = False

    def check(self, now: datetime) -> Optional[MonitorAction]:
        if self.acknowledged:
            return None
        if now - self.created_at >= timedelta(minutes=ESCALATION_TIMEOUT_MIN):
            return MonitorAction(
                "escalation_default_derisk",
                f"escalation unresolved past {ESCALATION_TIMEOUT_MIN:.0f} min: default action — "
                f"reduce {DEFAULT_DERISK_PCT:.0f}% (when in doubt and out of time, be smaller)",
                ticker=self.ticker)
        return None


def validate_escalation_action(action: str) -> str:
    """Escalation outputs are hold|reduce|hedge|exit — never entries, never increases (§9.5)."""
    if action not in ALLOWED_ESCALATION_ACTIONS:
        raise ValueError(f"escalation action {action!r} forbidden (allowed: {ALLOWED_ESCALATION_ACTIONS})")
    return action


@dataclass
class HeldPosition:
    ticker: str
    qty: int
    stop_price: Optional[float]
    direction: str                 # long | short
    last_mark: float
    mark_at: datetime


@dataclass
class MonitorTickResult:
    actions: list[MonitorAction]
    exit_only_names: set[str] = field(default_factory=set)


def monitor_tick(
    *,
    breakers: BreakerStateMachine,
    nav_usd: float,
    positions: list[HeldPosition],
    now: datetime,
    market_open: bool,
) -> MonitorTickResult:
    """One intraday check: breakers + per-trade stops + staleness. Market CLOSED ⇒ no breaker
    transitions off stale closed-market marks (R7.1's principle applied to monitoring)."""
    if not market_open:
        return MonitorTickResult(actions=[MonitorAction(
            "tick_skipped_market_closed", "market closed: marks stale, no breaker evaluation")])

    actions = breakers.tick(nav_usd)
    exit_only: set[str] = set()
    for p in positions:
        age_min = (now - p.mark_at).total_seconds() / 60.0
        if age_min > STALE_MARK_MAX_MIN:
            exit_only.add(p.ticker)
            actions.append(MonitorAction(
                "stale_exit_only",
                f"mark is {age_min:.0f} min old (> {STALE_MARK_MAX_MIN:.0f}): exit-only — adds "
                f"blocked, exits allowed (P1/P8)", ticker=p.ticker))
            continue  # a stale mark must not trigger a stop decision either
        if p.stop_price is not None:
            breached = (p.last_mark <= p.stop_price) if p.direction == "long" \
                else (p.last_mark >= p.stop_price)
            if breached:
                actions.append(MonitorAction(
                    "stop_exit", f"stop {p.stop_price} breached at mark {p.last_mark}: exit "
                                 f"(modeled/logged — the R2 wall applies)", ticker=p.ticker))
    for a in actions:
        logger.info("monitor_action", kind=a.kind, ticker=a.ticker, detail=a.detail)
    return MonitorTickResult(actions=actions, exit_only_names=exit_only)


class Watchdog:
    """R7.4 / P12 'silent loop': a monitor that misses its heartbeat is itself a breach → HALT."""

    def __init__(self, max_gap_min: float = 5.0):
        self.max_gap_min = max_gap_min
        self.last_heartbeat: Optional[datetime] = None

    def beat(self, now: datetime) -> None:
        self.last_heartbeat = now

    def check(self, now: datetime, breakers: BreakerStateMachine) -> Optional[MonitorAction]:
        if self.last_heartbeat is None:
            return None
        gap_min = (now - self.last_heartbeat).total_seconds() / 60.0
        if gap_min > self.max_gap_min:
            breakers.state = "halt"  # the silent monitor IS the breach (P12 HALT source)
            return MonitorAction("watchdog_halt",
                                 f"monitor silent {gap_min:.1f} min (> {self.max_gap_min}): HALT — "
                                 f"block approvals until human review (P12)")
        return None
