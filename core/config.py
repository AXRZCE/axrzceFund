"""Configuration loader and version hashing per architecture.md §7.3 and configuration.md."""

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class ConfigVersion:
    """Immutable configuration with its hash (config_version)."""

    config_version: str  # SHA256 of docs/configuration.md
    params: Dict[str, Any]  # All parameters from configuration.md
    timestamp: str  # ISO format, when config was loaded


class ConfigLoader:
    """Load and hash docs/configuration.md to produce config_version.

    Per configuration.md §11: config changes are versioned as deployments.
    The hash is a SHA256 of the raw .md file (exact bytes).
    """

    def __init__(self, config_file: Path = Path("docs/configuration.md")):
        self.config_file = config_file

    def load(self) -> ConfigVersion:
        """Load configuration.md and compute config_version hash.

        Returns:
            ConfigVersion with hashed version and parsed parameters.

        Raises:
            FileNotFoundError: if docs/configuration.md does not exist.
            ValueError: if critical parameters are missing or malformed.
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

        # Read raw bytes for hashing
        raw_bytes = self.config_file.read_bytes()
        config_version = hashlib.sha256(raw_bytes).hexdigest()[:12]  # 12-char short hash

        # Parse parameters from markdown
        params = self._parse_markdown(self.config_file.read_text())

        from datetime import datetime, timezone

        config = ConfigVersion(
            config_version=config_version,
            params=params,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "config_loaded",
            config_version=config_version,
            param_count=len(params),
            file=str(self.config_file),
        )

        return config

    @staticmethod
    def _parse_markdown(text: str) -> Dict[str, Any]:
        """Parse parameter values from markdown (naive but deterministic).

        Format: `name = value` — *rationale* (protocol where used).

        Returns a dict of {parameter_name: parsed_value}.
        Supports: strings, bools, floats, ints, lists. Tuples of [low, high] ranges.
        """
        params = {}

        for line in text.split("\n"):
            line = line.strip()

            # Skip comments, headings, empty lines
            if not line or line.startswith("#") or line.startswith("|"):
                continue

            # Match: `- name = value — *rationale*`
            if " = " not in line:
                continue

            try:
                # Extract name and value
                before_eq, after_eq = line.split(" = ", 1)

                # Remove leading `- ` and backticks from name
                name = before_eq.lstrip("- `").rstrip("`").strip()

                # Extract value (before the " — " or comment)
                if " — " in after_eq:
                    value_str = after_eq.split(" — ")[0].strip()
                else:
                    value_str = after_eq.strip()

                # Parse value type
                value_str = value_str.strip()
                if not value_str:
                    continue

                # Remove trailing commas, quotes
                value_str = value_str.rstrip(",").strip()

                # Try to parse as Python literal (int, float, bool, list, dict, string)
                if value_str.lower() == "true":
                    value = True
                elif value_str.lower() == "false":
                    value = False
                elif value_str.startswith("[") and value_str.endswith("]"):
                    # List or range [low, high]
                    try:
                        value = json.loads(value_str)
                    except json.JSONDecodeError:
                        value = value_str
                elif value_str.startswith("{") and value_str.endswith("}"):
                    # Dict
                    try:
                        value = json.loads(value_str)
                    except json.JSONDecodeError:
                        value = value_str
                else:
                    # Try int or float
                    try:
                        value = int(value_str)
                    except ValueError:
                        try:
                            value = float(value_str)
                        except ValueError:
                            # Treat as string (remove quotes if present)
                            value = value_str.strip('"\'')

                params[name] = value
            except Exception:
                # Skip malformed lines
                pass

        return params


def load_config(config_file: Path = Path("docs/configuration.md")) -> ConfigVersion:
    """Convenience function to load configuration."""
    return ConfigLoader(config_file).load()


if __name__ == "__main__":
    import sys

    try:
        cfg = load_config()
        print(f"Config version: {cfg.config_version}")
        print(f"Loaded {len(cfg.params)} parameters")
        print(f"Timestamp: {cfg.timestamp}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
