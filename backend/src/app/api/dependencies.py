"""FastAPI dependency-injection wiring for the controller layer.

Each `get_*` function is a small factory: FastAPI calls it per-request (or
resolves it from a cached dependency higher up the chain), and a route
declares what it needs via `Depends(...)` instead of importing a
module-level singleton directly. This is what makes `SessionService` (and
whatever agent/multi-agent services get added later) swappable in tests -
you override `get_session_service` on the `app`, not monkeypatch an import.
"""

from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.repositories.session_repository import SessionRepository
from app.services.agent_service import AgentService
from app.services.session_service import SessionService


def get_session_repository(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> SessionRepository:
    return SessionRepository(database)


def get_session_service(
    repository: Annotated[SessionRepository, Depends(get_session_repository)],
) -> SessionService:
    return SessionService(repository)


def get_graph(request: Request) -> CompiledStateGraph:
    """The compiled graph is built once at startup and stashed on
    `app.state` (see `main.py`'s lifespan) - this just exposes it through
    the same `Depends()` chain as everything else, so routes never reach
    into `request.app.state` themselves."""
    return request.app.state.graph


def get_agent_service(
    graph: Annotated[CompiledStateGraph, Depends(get_graph)],
) -> AgentService:
    return AgentService(graph)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]
