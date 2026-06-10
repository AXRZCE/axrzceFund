"""Structured logging setup per architecture.md §7.

All LLM calls logged with: model, tokens, cost, latency, prompt_version, agent_id, decision_id.
All system events logged to the append-only event log (L2).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import EventDict


def setup_logging(
    log_dir: Path = Path("var/logs"),
    log_file: str = "fund.log",
    level: str = "INFO",
) -> None:
    """Configure structlog for the fund.

    Args:
        log_dir: Directory for log files.
        log_file: Filename for structured logs.
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # Timestamp processor
    def add_timestamp(logger, method_name, event_dict: EventDict) -> EventDict:
        event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        return event_dict

    # JSON output processor
    def render_to_json(logger, method_name, event_dict: EventDict) -> str:
        return json.dumps(event_dict, default=str)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            add_timestamp,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging_level=getattr(
                __import__("logging"), level.upper(), __import__("logging").INFO
            )
        ),
    )


class LLMCallLogger:
    """Log every LLM call with model, tokens, cost, latency, versions."""

    def __init__(self):
        self.logger = structlog.get_logger()

    def log_call(
        self,
        agent_id: str,
        model: str,
        prompt_version: str,
        config_version: str,
        code_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
        decision_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> None:
        """Log an LLM call.

        Args:
            agent_id: Which agent made the call (e.g., "FUND-TECH", "BULL-01").
            model: Model name/ID used.
            prompt_version: Version of the prompt template.
            config_version: Configuration version hash (from config.py).
            code_version: Git SHA or code version.
            input_tokens: Tokens in the prompt.
            output_tokens: Tokens in the completion.
            cost_usd: Estimated cost in USD.
            latency_ms: Roundtrip latency in milliseconds.
            decision_id: Optional identifier for the trade/decision being made.
            cycle_id: Optional identifier for the daily cycle.
        """
        self.logger.info(
            "llm_call",
            agent_id=agent_id,
            model=model,
            prompt_version=prompt_version,
            config_version=config_version,
            code_version=code_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            total_tokens=input_tokens + output_tokens,
            decision_id=decision_id,
            cycle_id=cycle_id,
        )


class EventLogger:
    """Log system events to the append-only event log (L2)."""

    def __init__(self, event_log_path: Path = Path("var/event_log.jsonl")):
        self.event_log_path = event_log_path
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = structlog.get_logger()

    def log_event(
        self,
        event_type: str,
        cycle_id: str,
        decision_ts: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Log an event to the append-only event log.

        Args:
            event_type: Type of event (e.g., "memo_written", "ballot_cast", "order_submitted").
            cycle_id: Which cycle this event belongs to.
            decision_ts: The decision_ts boundary (ISO format).
            **kwargs: Additional event data.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "cycle_id": cycle_id,
            "decision_ts": decision_ts,
            **kwargs,
        }

        # Append to JSONL file
        with open(self.event_log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

        # Also log via structlog
        self.logger.info(
            "event_logged",
            event_type=event_type,
            cycle_id=cycle_id,
        )


if __name__ == "__main__":
    # Test setup
    setup_logging()
    logger = structlog.get_logger()
    logger.info("hello", message="test logging")

    llm_logger = LLMCallLogger()
    llm_logger.log_call(
        agent_id="FUND-TECH",
        model="claude-opus-4-8",
        prompt_version="v1.0",
        config_version="abc123def456",
        code_version="deadbeef",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.045,
        latency_ms=1200,
    )
