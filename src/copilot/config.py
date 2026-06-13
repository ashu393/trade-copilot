"""Central configuration, loaded from environment / .env.

Keeping all tunables (model names, safety limits, paths) in one typed object
makes the system easy to configure per-environment and easy to test.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (src/copilot/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
KB_DIR = DATA_DIR / "knowledge_base"
OUTPUTS_DIR = REPO_ROOT / "outputs"


class Settings(BaseSettings):
    """Runtime settings. Values come from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="",
        extra="ignore",
    )

    anthropic_api_key: str = "sk-ant-REPLACE_ME"

    # Model selection (env: COPILOT_SQL_MODEL, COPILOT_COMPOSE_MODEL)
    copilot_sql_model: str = "claude-sonnet-4-5"
    copilot_compose_model: str = "claude-sonnet-4-5"

    # SQL safety limits
    copilot_max_result_rows: int = 1000
    copilot_sql_timeout_s: int = 10

    @property
    def has_real_api_key(self) -> bool:
        """True when a non-placeholder key is configured.

        Lets the system fall back to a deterministic offline stub so the whole
        pipeline runs end-to-end without a live key (useful for tests/demo).
        """
        return bool(self.anthropic_api_key) and "REPLACE_ME" not in self.anthropic_api_key


settings = Settings()
