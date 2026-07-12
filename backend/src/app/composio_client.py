"""Composio SDK client construction - shared infrastructure, same pattern
as `db.py` for Motor.

Composio's `provider` determines what *shape* `tools.get()` returns (plain
OpenAI-style dict schemas by default, or framework-specific objects) - it's
fixed at client construction, not swappable per call. That's why there are
two separate cached clients here rather than one:

  * `get_composio_client()` - default provider, used for connection
    management (`services/integration_service.py`, Phase 1) which never
    touches tool schemas at all.
  * `get_composio_langchain_client()` - Composio's LangChain provider, used
    to fetch ready-to-bind `langchain_core.tools.BaseTool` objects for the
    Gmail/LinkedIn specialist agents (Phase 2/3) - verified live before
    writing those.
"""

from functools import lru_cache

from composio import Composio
from composio_langchain import LangchainProvider

from app.config import settings


@lru_cache
def get_composio_client() -> Composio:
    """Lazily constructed, cached for the process lifetime - same pattern as
    `config.get_settings()`. Deferred rather than built at import time
    because `Composio(api_key=...)` raises immediately if no key is
    configured (confirmed live), and the test suite never configures one -
    it never hits an integrations/agent route, so it must never be forced
    to construct this client just by importing this module.
    """
    return Composio(api_key=settings.composio_api_key)


@lru_cache
def get_composio_langchain_client() -> Composio:
    """Same deferred-construction reasoning as `get_composio_client()`,
    just with `LangchainProvider()` set so `tools.get(...)` returns
    ready-to-bind `BaseTool` objects instead of plain dict schemas."""
    return Composio(api_key=settings.composio_api_key, provider=LangchainProvider())
