"""Pytest fixtures shared by all tests.

Sets test-only environment variables BEFORE any `app.*` module is imported,
since app/config.py and app/db.py build their singletons (Settings, the
Motor client) at import time. This keeps tests off the real
`agentic_ai_chat` database used by `make dev`.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-placeholder-key")
os.environ.setdefault("MONGO_DB_NAME", "agentic_ai_chat_test")

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_database
from app.main import app


@pytest.fixture
async def client():
    """An httpx client wired directly to the FastAPI app (no real socket),
    with the lifespan running so `app.state.graph` gets built."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    # Clean up the test database so repeated runs start fresh.
    await get_database().client.drop_database(os.environ["MONGO_DB_NAME"])
