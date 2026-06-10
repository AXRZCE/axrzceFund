"""Tests for config loader, replay tuple, and logging utilities."""

import pytest
from pathlib import Path
from core.config import ConfigLoader, load_config
from core.replay import (
    new_trade_id,
    new_cycle_id,
    new_replay_tuple,
    ReplayTuple,
)


class TestConfigLoader:
    """Test configuration loading and versioning."""

    def test_load_config_from_docs(self):
        """Load configuration.md and verify it has a hash."""
        cfg = load_config(Path("docs/configuration.md"))

        assert cfg.config_version, "config_version should be non-empty"
        assert len(cfg.config_version) > 0, "config_version should be > 0 chars"
        assert cfg.params, "Should parse at least some parameters"
        assert cfg.timestamp, "Should have timestamp"

    def test_config_version_is_stable(self):
        """Loading the same file twice produces the same config_version."""
        cfg1 = load_config(Path("docs/configuration.md"))
        cfg2 = load_config(Path("docs/configuration.md"))

        assert cfg1.config_version == cfg2.config_version, "Hash should be deterministic"

    def test_config_params_parsed(self):
        """Configuration parameters are parsed from markdown."""
        cfg = load_config(Path("docs/configuration.md"))

        # We expect to find at least some known parameters from the doc
        # (exact names depend on the markdown format; these are examples)
        assert "universe" in cfg.params or len(cfg.params) > 5, (
            "Should parse universe or have other parameters"
        )


class TestReplayTuple:
    """Test replay tuple generation."""

    def test_new_trade_id(self):
        """Generate trade IDs."""
        t1 = new_trade_id()
        t2 = new_trade_id()

        assert t1.startswith("trade_"), "Should have trade_ prefix"
        assert t1 != t2, "Each trade ID should be unique"

    def test_new_cycle_id(self):
        """Generate cycle IDs."""
        c1 = new_cycle_id(1, "20260610")
        c2 = new_cycle_id(2, "20260610")

        assert c1.startswith("cycle_"), "Should have cycle_ prefix"
        assert "20260610" in c1, "Should include date"
        assert "_0001" in c1, "Should include padded number"
        assert c1 != c2, "Different cycle numbers should produce different IDs"

    def test_new_replay_tuple(self):
        """Create a replay tuple."""
        cycle = new_cycle_id(1, "20260610")
        trade = new_trade_id()

        replay = new_replay_tuple(
            cycle_id=cycle,
            trade_id=trade,
            agent_id="FUND-TECH",
            prompt_version="v1.0",
            model_version="claude-opus-4-8",
            config_version="abc123",
            code_version="deadbeef",
        )

        assert replay.trade_id == trade
        assert replay.cycle_id == cycle
        assert replay.agent_id == "FUND-TECH"
        assert replay.prompt_version == "v1.0"
        assert replay.config_version == "abc123"

        # Should be serializable
        d = replay.to_dict()
        assert isinstance(d, dict)
        assert d["trade_id"] == trade


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
