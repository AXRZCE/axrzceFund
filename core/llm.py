"""Metered OpenRouter client (WP2, R4) — OpenAI-compatible gateway to every model family.

One client, one key (`OPENROUTER_API_KEY`). Each call:
  - pins the OpenRouter backend (the manifest's `provider` pin, `allow_fallbacks: false`) so what
    ran is fully determined for replay; and
  - records the REAL per-call token counts + USD cost. OpenRouter returns `cost` inline in `usage`
    when `usage: {include: true}` is set, so the cost is the gateway's actual charge — not a guess.

Anti-hoax (R4): if no real cost comes back, `call()` raises rather than recording a fabricated
zero/estimate; the metering test asserts a non-zero cost, so gutting it goes red.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog
from dotenv import load_dotenv
from openai import OpenAI

logger = structlog.get_logger()

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class LLMError(Exception):
    """OpenRouter call failed, or no real usage/cost came back to meter."""


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float  # OpenRouter's actual charge for the call (from usage.cost)

    @property
    def is_metered(self) -> bool:
        return self.total_tokens > 0 and self.cost_usd > 0.0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model_version: str          # the model that actually ran (response.model)
    provider: dict              # the provider pin applied to this call
    usage: LLMUsage
    generation_id: Optional[str]
    finish_reason: Optional[str]


def _load_key() -> str:
    if not os.getenv("OPENROUTER_API_KEY"):
        # explicit .env at the project root (a bare load_dotenv() can miss it in some contexts)
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY not set (.env or environment)")
    return key


def _extract_cost(usage: Any) -> Optional[float]:
    """Pull OpenRouter's real USD `cost` off the usage object. The OpenAI SDK surfaces this
    extra field via attribute / model_extra / model_dump depending on version."""
    c = getattr(usage, "cost", None)
    if c is None:
        extra = getattr(usage, "model_extra", None) or {}
        c = extra.get("cost")
    if c is None:
        try:
            c = usage.model_dump().get("cost")
        except Exception:
            c = None
    return float(c) if c is not None else None


class OpenRouterClient:
    """Metered OpenRouter client. `call()` returns a metered `LLMResponse` or raises `LLMError`."""

    def __init__(self, *, timeout: float = 120.0):
        self._key = _load_key()
        self._client = OpenAI(base_url=OPENROUTER_BASE, api_key=self._key, timeout=timeout)

    def call(
        self,
        *,
        model_version: str,
        messages: list[dict],
        provider: dict,
        response_format: Optional[dict] = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model_version,
            "messages": messages,
            "max_tokens": max_tokens,
            # provider pin (replay) + ask OpenRouter to include the real cost in usage (R4)
            "extra_body": {"provider": provider, "usage": {"include": True}},
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"OpenRouter call failed for {model_version!r}: {e}") from e

        if not resp.choices:
            raise LLMError(f"no choices returned for {model_version!r}")
        choice = resp.choices[0]

        u = resp.usage
        if u is None:
            raise LLMError(f"no usage returned for {model_version!r} — cannot meter (R4)")
        cost = _extract_cost(u)
        if cost is None:
            raise LLMError(
                f"no real cost in usage for {model_version!r} (gen {getattr(resp, 'id', None)}); "
                "refusing to record a guessed cost — R4 requires the gateway's actual charge"
            )

        usage = LLMUsage(
            prompt_tokens=int(u.prompt_tokens),
            completion_tokens=int(u.completion_tokens),
            total_tokens=int(u.total_tokens),
            cost_usd=cost,
        )
        logger.info(
            "llm_call",
            model=resp.model,
            provider=provider,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
            gen_id=getattr(resp, "id", None),
        )
        return LLMResponse(
            text=choice.message.content or "",
            model_version=resp.model,
            provider=provider,
            usage=usage,
            generation_id=getattr(resp, "id", None),
            finish_reason=choice.finish_reason,
        )
