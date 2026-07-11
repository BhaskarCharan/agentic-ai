"""FastAPI application entrypoint.

Run via `make dev` (see ../Makefile), which just calls:
    uvicorn app.main:app --reload --app-dir src
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_graph
from app.api import chat, sessions
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The compiled graph holds the MongoDB checkpointer connection, so it's
    # built exactly once at startup and stashed on `app.state` - every
    # request handler reads it from there instead of rebuilding it.
    app.state.graph = build_graph()
    yield


app = FastAPI(title="Agentic AI Chat Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
