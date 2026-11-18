"""Application settings, read from the repo-root `.env` (see `.env.example`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """All runtime configuration in one typed object.

    Read once via `get_settings()`; providers, ingestion and the API take values from here instead
    of reading `os.environ`. Secrets are `SecretStr` so they never print in logs or reprs.
    pydantic-settings reads `.env` without exporting it to `os.environ`, so an `ANTHROPIC_API_KEY`
    in `.env` does not reach the Claude Code subprocess. A key exported in the shell itself still
    would (and would bill the API, not the plan); `ChatClaudeCode` logs a warning when it sees one.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: Literal["claude_code", "anthropic_api", "fake"] = "claude_code"
    anthropic_api_key: SecretStr | None = None
    # Owner decision 2026-11-17: Haiku for routing and extraction, Sonnet for answers and plans.
    model_fast: str = "claude-haiku-5-5"
    model_smart: str = "claude-sonnet-5-5"

    voyage_api_key: SecretStr | None = None
    embed_model: str = "voyage-4"
    # Voyage limits without a payment method: 3 requests and ~10K tokens per minute.
    voyage_rpm: int = 3
    voyage_tpm: int = 10_000

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_local_path: str = "backend/data/qdrant"  # relative to the repo root
    qdrant_collection: str = "gradpath_kb"

    # Chunking (characters); tuned later by the chunk-size experiment in EVALUATION.md.
    chunk_size: int = 1200
    chunk_overlap: int = 150

    # Retrieval. min_score is cosine similarity; below it a chunk is not treated as evidence.
    # Provisional value, calibrated on real queries (T-001) and then by the retrieval eval.
    retrieval_k: int = 5
    retrieval_min_score: float = 0.45  # probe 2026-11-17: covered >= 0.59, uncovered <= 0.39

    langsmith_tracing: bool = False
    langsmith_project: str = "gradpath-dev"

    app_mode: Literal["demo", "live"] = "demo"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests override with `Settings(...)` directly)."""
    return Settings()
