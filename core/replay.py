"""Replay tuple stamping and replayability per architecture.md §7.3.

Every artifact carries: (agent_id, prompt_version, model_version, manifest_version,
config_version, code_version). This enables exact reconstruction of any past decision.

`manifest_version` (WP3 R5, closes SF-2) is the deploy-manifest hash — DISTINCT from
`config_version` (the configuration.md hash). A model/roster swap in deploy/model_manifest.yaml
changes `manifest_version`, so it must change the replay identity; before WP3 the manifest hash
had no field of its own and WP2 stamped it into `config_version` (a conflation now corrected).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


@dataclass
class ReplayTuple:
    """Immutable replay identity for every decision/artifact.

    Enables exact reconstruction: given this tuple + the event log + the point-in-time data,
    any past decision is deterministically replayable.
    """

    trade_id: str  # Unique identifier for this trade/decision
    cycle_id: str  # Which daily cycle this belongs to
    decision_ts: str  # The information boundary (ISO format, always decision time)
    agent_id: str  # Which agent produced the artifact
    prompt_version: str  # Version of the agent's system prompt
    model_version: str  # Which model+version (e.g., "claude-opus-4-8", "gpt-4-turbo-1106")
    manifest_version: str  # Deploy-manifest hash (deploy/model_manifest.yaml) — a roster/model swap changes it
    config_version: str  # configuration.md hash (fund bylaws) — DISTINCT from manifest_version
    code_version: str  # Git SHA or build identifier

    def to_dict(self) -> dict:
        """Convert to dict for logging/serialization."""
        return {
            "trade_id": self.trade_id,
            "cycle_id": self.cycle_id,
            "decision_ts": self.decision_ts,
            "agent_id": self.agent_id,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "manifest_version": self.manifest_version,
            "config_version": self.config_version,
            "code_version": self.code_version,
        }


def new_trade_id() -> str:
    """Generate a unique trade identifier."""
    return f"trade_{uuid4().hex[:12]}"


def new_cycle_id(cycle_number: int, date_str: Optional[str] = None) -> str:
    """Generate a cycle identifier.

    Args:
        cycle_number: Sequential cycle number.
        date_str: Optional date string (YYYY-MM-DD); defaults to today.

    Returns:
        Cycle ID like "cycle_20260610_0001".
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"cycle_{date_str}_{cycle_number:04d}"


def decision_timestamp() -> str:
    """Current timestamp in ISO format for decision_ts."""
    return datetime.now(timezone.utc).isoformat()


def new_replay_tuple(
    cycle_id: str,
    agent_id: str,
    prompt_version: str,
    model_version: str,
    manifest_version: str,
    config_version: str,
    code_version: str,
    trade_id: Optional[str] = None,
) -> ReplayTuple:
    """Create a new replay tuple for an agent artifact.

    Args:
        cycle_id: Which cycle.
        agent_id: Which agent.
        prompt_version: Version of prompt.
        model_version: Model used.
        manifest_version: Deploy-manifest hash (deploy/model_manifest.yaml).
        config_version: configuration.md hash (distinct from manifest_version).
        code_version: Code version.
        trade_id: Optional existing trade ID; generates one if not provided.

    Returns:
        A ReplayTuple ready for logging into an artifact.
    """
    if trade_id is None:
        trade_id = new_trade_id()

    return ReplayTuple(
        trade_id=trade_id,
        cycle_id=cycle_id,
        decision_ts=decision_timestamp(),
        agent_id=agent_id,
        prompt_version=prompt_version,
        model_version=model_version,
        manifest_version=manifest_version,
        config_version=config_version,
        code_version=code_version,
    )


if __name__ == "__main__":
    # Test
    cycle = new_cycle_id(1)
    trade = new_trade_id()
    replay = new_replay_tuple(
        cycle_id=cycle,
        trade_id=trade,
        agent_id="FUND-TECH",
        prompt_version="v1.0",
        model_version="claude-opus-4-8",
        manifest_version="mani12345678",
        config_version="abc123def456",
        code_version="deadbeef",
    )
    print(f"Cycle: {cycle}")
    print(f"Trade: {trade}")
    print(f"Replay tuple: {replay}")
