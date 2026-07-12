"""
Central application configuration.

We use pydantic-settings so every config value is validated and typed, and
can be overridden by environment variables or a local `.env` file without
touching code. This is the ONLY place in the app that reads `os.environ`
directly (via pydantic) - everything else imports `settings` from here.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic-settings to also load values from a `.env` file in the
    # backend/ directory (in addition to real environment variables, which
    # always take precedence).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- LLM ---
    google_api_key: str
    model_name: str = "gemini-flash-latest"

    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "agentic_ai_chat"

    # --- CORS ---
    # Comma-separated list of origins the Angular dev server (or prod build)
    # is served from, e.g. "http://localhost:4200,https://myapp.com".
    cors_origins: str = "http://localhost:4200"

    # --- LangSmith tracing (optional) ---
    # Off by default - a demo/dev project shouldn't silently start shipping
    # every conversation to a third-party service. Flip on in `.env`.
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "agentic-ai-chat"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # --- Composio (Gmail/LinkedIn account linking - MULTI_AGENT_ROADMAP.md
    # Phase 1+) ---
    # Defaults to "" rather than being required: this app has no real user
    # auth (see DEVELOPMENT_LOG.md), so every Composio call uses one fixed
    # identifier for the single person using this app locally, not a
    # per-request authenticated user.
    composio_api_key: str = ""
    composio_user_id: str = "me"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def _export_langsmith_env(settings: Settings) -> None:
    """Bridge our typed settings into the raw `os.environ` vars the
    `langsmith`/`langchain-core` tracer actually reads.

    LangSmith's tracing is auto-instrumented deep inside LangChain/LangGraph
    (every LLM/tool call checks `os.environ` for `LANGSMITH_TRACING`, not
    anything of ours) - there's no `enable_tracing()` call to make, no
    callback to wire in. That means it's the one place in the app that
    deliberately writes to `os.environ` rather than just reading from it:
    `.env`/real env vars stay the single source of truth (so this doesn't
    conflict with the module docstring's rule above), and this function is
    just what makes a third-party library's own env-var lookup see them.
    """
    if not settings.langsmith_tracing:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings accessor.

    FastAPI route handlers can depend on this via `Depends(get_settings)`,
    and since it's lru_cache'd, the .env file is only read/parsed once per
    process instead of on every request.
    """
    return Settings()


# Convenience module-level instance for non-FastAPI code (e.g. the agent
# graph, which is built once at import time, not per-request).
settings = get_settings()
_export_langsmith_env(settings)
