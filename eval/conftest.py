"""Test-session configuration.

The suite must be deterministic, free, and runnable without network access or a
live API key. We therefore force the offline `StubLLM` for the whole session by
neutralising the configured key, regardless of any real `ANTHROPIC_API_KEY`
present in the environment or `.env`. (Live-model behaviour is exercised
manually / via the eval CLI, not in unit tests.)
"""

from __future__ import annotations

import pytest

from copilot.config import settings


@pytest.fixture(autouse=True, scope="session")
def _force_offline_stub():
    original = settings.anthropic_api_key
    settings.anthropic_api_key = "sk-ant-REPLACE_ME"  # -> has_real_api_key == False
    yield
    settings.anthropic_api_key = original
