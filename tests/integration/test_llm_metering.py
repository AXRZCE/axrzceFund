"""R4 — the metered OpenRouter client records the gateway's REAL per-call token cost (live API).

Integration test: makes one tiny real call (fractions of a cent). Skipped when no
OPENROUTER_API_KEY is available. Anti-hoax: the cost/token assertions are non-zero, so gutting
the metering to a guessed/zero cost turns this red.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from core.llm import LLMUsage, OpenRouterClient  # noqa: E402

# Only the LIVE call is integration + key-gated, so a default `-m 'not integration'` run never
# fires it; the pure-unit is_metered test below is NOT gated and always runs.
_needs_key = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — live OpenRouter metering test skipped",
)


@pytest.mark.integration
@_needs_key
def test_metered_call_records_real_cost():
    client = OpenRouterClient()
    r = client.call(
        model_version="google/gemini-2.5-flash-lite",
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        provider={"only": ["google-vertex"], "allow_fallbacks": False},
        max_tokens=10,
    )
    assert r.text.strip(), "expected a non-empty completion"
    assert r.usage.prompt_tokens > 0
    assert r.usage.completion_tokens > 0
    assert r.usage.total_tokens == r.usage.prompt_tokens + r.usage.completion_tokens
    assert r.usage.cost_usd > 0.0, "R4: a real, non-zero USD cost must be recorded"
    assert r.usage.is_metered
    assert r.generation_id and r.generation_id.startswith("gen-")
    assert r.model_version.startswith("google/")


def test_is_metered_property():
    assert LLMUsage(5, 1, 6, 9e-07).is_metered
    assert not LLMUsage(0, 0, 0, 0.0).is_metered          # nothing ran
    assert not LLMUsage(5, 1, 6, 0.0).is_metered          # tokens but zero cost (gutted) -> not metered
