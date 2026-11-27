"""Application settings, read from the repo-root `.env` (see `.env.example`)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
# Most critic -> revise rounds allowed (each is a Sonnet call); used by Settings and workflows.
MAX_REVISIONS_CAP = 3


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
    # Cost protection on the deployed server (never local mode): public search off switch, a
    # persistent cap on query embeddings per UTC day and in total, and a persistent query cache.
    search_enabled: bool = True
    embed_budget_daily: int = Field(default=300, ge=0)
    embed_budget_total: int = Field(default=20_000, ge=0)
    query_cache_max: int = Field(default=10_000, ge=0)
    usage_collection: str = "gradpath_usage"
    query_cache_collection: str = "gradpath_query_cache"

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_local_path: str = "backend/data/qdrant"  # relative to the repo root
    # Target of `ingestion.copy_index` only (T-020): the deployed index. Separate from qdrant_url
    # so setting it never points local runs at the cloud. The deployed server uses qdrant_url.
    qdrant_cloud_url: str | None = None
    qdrant_cloud_api_key: SecretStr | None = None
    qdrant_collection: str = "gradpath_kb"

    # Chunking (characters); tuned later by the chunk-size experiment in EVALUATION.md.
    chunk_size: int = 1200
    chunk_overlap: int = 150

    # Retrieval. min_score is cosine similarity; below it a chunk is not treated as evidence.
    # Provisional value, calibrated on real queries (T-001) and then by the retrieval eval.
    retrieval_k: int = 5
    retrieval_min_score: float = 0.45  # probe 2026-11-17: covered >= 0.59, uncovered <= 0.39

    # Tracing rules live in tracing.py: off unless true AND a key is set; only in local mode.
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "gradpath-dev"

    # Career workflow (T-003): critic -> revise rounds before finalizing. Owner decision 2026-11-18:
    # 1 by default; capped because each round is a Sonnet call on the owner's plan.
    workflow_max_revisions: int = Field(default=1, ge=0, le=MAX_REVISIONS_CAP)
    # Wall-clock budget for one workflow run (T-006, owner decision 2026-11-18: 300 s). Checked
    # between steps; past it, the run ends in a labelled fallback. A real run took ~100 s.
    workflow_time_budget_s: int = Field(default=300, ge=30, le=1800)
    # Route log for POST /api/assist (T-006): one JSON line per request, no request text.
    # Relative to the repo root; "" turns it off. `logs/` is gitignored.
    route_log_path: str = "logs/routes.jsonl"

    # T-018 (owner decision 2026-11-20): local = the owner's machine, server credentials, tracing
    # allowed; demo = deployed, recorded runs only, model routes off; live = deployed, recordings
    # plus model routes with a visitor's key. Default demo: the safest, and it needs no keys.
    app_mode: Literal["local", "demo", "live"] = "demo"
    # Live mode's shared passcode (T-018 step 7, owner decision): visitors send it in the
    # X-GradPath-Passcode header; live refuses to start without one of 16+ characters.
    live_passcode: SecretStr | None = None
    # Proxies in front of the API that append to X-Forwarded-For (Render: set in Milestone 8).
    # 0 = use the connection address; never trust the client-written left end of the header.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Browser origins allowed to POST (T-018 step 8, CSRF defence in depth): comma-separated, exact
    # scheme://host[:port]. Requests with no Origin header (curl, CLIs) are unaffected. There is
    # no CORS middleware: the browser only calls its own origin, through Next's /api proxy.
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Recorded runs served in every mode (relative to the repo root).
    demo_runs_path: str = "demo_runs"
    # Index summary written by ingest, read by the API for "Sources as of" (T-018 step 3).
    index_info_path: str = "knowledge_base/index_info.json"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests override with `Settings(...)` directly)."""
    return Settings()
