"""OpenRouterClient hardening — fail-closed on empty/degenerate responses (pure unit, no network).

Anti-hoax: the client must NEVER return a zero-cost no-op. A degenerate response (0 tokens / blank
completion / non-positive cost) is retried a bounded number of times (each attempt logged) and then
raises LLMError. This complements the live R4 metering test (tests/integration/test_llm_metering.py).
These tests inject fake responses, so they need neither a key nor the network and always run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.llm import LLMError, OpenRouterClient


# ── minimal fakes mimicking the OpenAI SDK response shape the client reads ────────
@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg
    finish_reason: str = "stop"


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: object  # float, or None to simulate "no real cost"


@dataclass
class _Resp:
    choices: list
    usage: object
    model: str = "google/gemini-2.5-flash-lite"
    id: str = "gen-test"


class _FakeCompletions:
    """Returns queued responses in order (last one repeats); an Exception item is raised."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        return r


class _FakeClient:
    def __init__(self, responses):
        self.chat = type("C", (), {"completions": _FakeCompletions(responses)})()


def _client(monkeypatch, responses) -> OpenRouterClient:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-used")
    c = OpenRouterClient()
    c._client = _FakeClient(responses)  # no real network
    return c


_ARGS = dict(model_version="m", messages=[{"role": "user", "content": "x"}],
             provider={"only": ["google-vertex"]}, max_retries=2, backoff_s=0)

_GOOD = _Resp(choices=[_Choice(_Msg("a real answer"))], usage=_Usage(10, 5, 15, 0.0004))
_EMPTY = _Resp(choices=[_Choice(_Msg(""))], usage=_Usage(0, 0, 0, 0.0))          # 0 tokens, blank, $0
_NOCOST = _Resp(choices=[_Choice(_Msg("text"))], usage=_Usage(10, 5, 15, None))  # unmeterable (R4)


def test_degenerate_response_fails_closed(monkeypatch):
    c = _client(monkeypatch, [_EMPTY, _EMPTY, _EMPTY])
    with pytest.raises(LLMError, match="degenerate|after 3 attempt"):
        c.call(**_ARGS)
    assert c._client.chat.completions.calls == 3  # initial + 2 retries, then raise


def test_no_cost_fails_closed_R4(monkeypatch):
    # A response with no real cost is unmeterable — R4 forbids a guessed cost, so it must raise.
    c = _client(monkeypatch, [_NOCOST, _NOCOST, _NOCOST])
    with pytest.raises(LLMError):
        c.call(**_ARGS)


def test_retries_then_succeeds(monkeypatch):
    # Two degenerate blips then a real metered response — the client retries and returns the good one.
    c = _client(monkeypatch, [_EMPTY, _EMPTY, _GOOD])
    r = c.call(**_ARGS)
    assert r.text == "a real answer"
    assert r.usage.cost_usd == 0.0004 and r.usage.total_tokens == 15
    assert r.usage.is_metered
    assert c._client.chat.completions.calls == 3


def test_transport_error_is_retried_then_raises(monkeypatch):
    c = _client(monkeypatch, [RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")])
    with pytest.raises(LLMError, match="after 3 attempt"):
        c.call(**_ARGS)


def test_retries_logged_to_event_log(monkeypatch):
    # No silent retries: each failed attempt is appended to the event log when one is provided.
    events = []
    fake_log = type("L", (), {"append": lambda self, **kw: events.append(kw)})()
    c = _client(monkeypatch, [_EMPTY, _GOOD])
    c.call(**_ARGS, event_log=fake_log, cycle_id="cycle_test")
    assert any(e["event_type"] == "llm_retry" and e["cycle_id"] == "cycle_test" for e in events)
