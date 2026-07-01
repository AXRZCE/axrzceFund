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
import time
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

    _DEGENERATE = "empty/degenerate response"

    def call(
        self,
        *,
        model_version: str,
        messages: list[dict],
        provider: dict,
        response_format: Optional[dict] = None,
        max_tokens: int = 4096,
        max_retries: int = 2,
        backoff_s: float = 1.0,
        event_log: Optional[Any] = None,
        cycle_id: str = "",
    ) -> LLMResponse:
        """Make one metered call, retrying a bounded number of times on an errored or empty/
        degenerate response (0 tokens / blank completion / non-positive cost), then FAIL-CLOSED
        (raise LLMError) — never return a zero-cost no-op. Every failed attempt is logged (structlog,
        and the event log when given); no silent retries. The R4 anti-hoax (a real cost must come
        back) is preserved: a costless response is degenerate and, after retries, raises."""
        kwargs: dict[str, Any] = {
            "model": model_version,
            "messages": messages,
            "max_tokens": max_tokens,
            # provider pin (replay) + ask OpenRouter to include the real cost in usage (R4)
            "extra_body": {"provider": provider, "usage": {"include": True}},
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        last = "no attempt made"
        for attempt in range(max_retries + 1):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                r = self._to_response(resp, model_version, provider)
                if r.usage.total_tokens == 0 or not r.text.strip() or r.usage.cost_usd <= 0.0:
                    raise LLMError(
                        f"{self._DEGENERATE} (tokens={r.usage.total_tokens}, "
                        f"cost={r.usage.cost_usd}, text_len={len(r.text.strip())})"
                    )
                logger.info(
                    "llm_call", model=r.model_version, provider=provider,
                    prompt_tokens=r.usage.prompt_tokens, completion_tokens=r.usage.completion_tokens,
                    cost_usd=r.usage.cost_usd, gen_id=r.generation_id, attempt=attempt + 1,
                )
                return r
            except LLMError as e:
                last = str(e)
            except Exception as e:  # transport / SDK error — also retryable
                last = f"transport error: {e}"
            self._log_retry(attempt, max_retries, model_version, last, event_log, cycle_id)
            if attempt < max_retries:
                time.sleep(backoff_s * (attempt + 1))  # linear backoff
        raise LLMError(
            f"OpenRouter call for {model_version!r} failed after {max_retries + 1} attempt(s): {last}"
        )

    def _to_response(self, resp: Any, model_version: str, provider: dict) -> LLMResponse:
        """Raw SDK response -> metered LLMResponse, raising LLMError if it cannot be metered
        (no choices / no usage / no real cost — the R4 anti-hoax)."""
        if not getattr(resp, "choices", None):
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
            prompt_tokens=int(u.prompt_tokens), completion_tokens=int(u.completion_tokens),
            total_tokens=int(u.total_tokens), cost_usd=cost,
        )
        return LLMResponse(
            text=choice.message.content or "", model_version=resp.model, provider=provider,
            usage=usage, generation_id=getattr(resp, "id", None), finish_reason=choice.finish_reason,
        )

    @staticmethod
    def _log_retry(attempt: int, max_retries: int, model_version: str, reason: str,
                   event_log: Optional[Any], cycle_id: str) -> None:
        """Log a failed attempt — never silent. structlog always; the event log too when provided."""
        logger.warning("llm_retry", model=model_version, attempt=attempt + 1,
                       of=max_retries + 1, reason=reason)
        if event_log is not None:
            try:
                event_log.append(
                    event_type="llm_retry", cycle_id=cycle_id or "unknown",
                    payload={"model": model_version, "attempt": attempt + 1,
                             "of": max_retries + 1, "reason": reason},
                )
            except Exception:  # logging must never break the call path
                pass
