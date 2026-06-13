"""LLM client abstraction.

A thin `LLMClient` protocol sits in front of Anthropic Claude so the rest of the
system (SQL generation, answer composition, the agent) depends on an interface,
not a vendor SDK. That makes the pipeline testable (inject a fake) and lets it
degrade gracefully to a deterministic offline stub when no real API key is set.

The Anthropic implementation uses prompt caching on the system prompt — the
schema card and instructions are large and identical across calls, so caching
them cuts both latency and token cost.
"""

from __future__ import annotations

import json
from typing import Protocol

from .config import settings


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        """Return the model's text completion for a system+user prompt."""
        ...


class AnthropicLLM:
    """Production client backed by the Anthropic Messages API with prompt caching."""

    def __init__(self, model: str, api_key: str | None = None):
        from anthropic import Anthropic

        self.model = model
        self._client = Anthropic(api_key=api_key or settings.anthropic_api_key)

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            # Cache the (large, stable) system prompt across calls.
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class StubLLM:
    """Deterministic offline stub used when no real API key is configured.

    It does NOT attempt general text-to-SQL. For the known evaluation questions
    it returns reference SQL/intent from `offline_fixtures`, so the full
    execute -> guard -> compose pipeline can be demonstrated and tested without
    a live model. For anything else it returns a structured "unsupported"
    response so behaviour stays predictable.
    """

    def __init__(self, model: str = "stub"):
        self.model = model

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        from .offline_fixtures import stub_response

        return json.dumps(stub_response(system=system, user=user))


def make_llm(model: str) -> LLMClient:
    """Factory: real Claude client if a key is present, else the offline stub."""
    if settings.has_real_api_key:
        return AnthropicLLM(model=model)
    return StubLLM(model=model)
