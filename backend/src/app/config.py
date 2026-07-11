"""
Central application configuration.

We use pydantic-settings so every config value is validated and typed, and
can be overridden by environment variables or a local `.env` file without
touching code. This is the ONLY place in the app that reads `os.environ`
directly (via pydantic) - everything else imports `settings` from here.
"""

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


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
