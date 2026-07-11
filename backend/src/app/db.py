"""
MongoDB access layer.

There are two different "consumers" of MongoDB in this app:
  1. LangGraph's own MongoDB checkpointer (see agent/graph.py) - it manages
     its own collections ("checkpoints", "checkpoint_writes") automatically.
     We do NOT touch those collections directly anywhere in this file.
  2. Our own `sessions` collection, which just stores metadata about each
     conversation (title, timestamps) so the frontend can render a sidebar
     list of past chats. The actual message content lives in LangGraph's
     checkpoints, keyed by the same `thread_id` we use as `_id` here.

We use Motor (the async MongoDB driver) since the whole API is async
end-to-end (FastAPI + LangGraph's async graph execution).
"""

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.db_models import SessionDocument

# A single shared client for the process lifetime. Motor's client is safe to
# share across requests/coroutines - it manages its own connection pool.
mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri)
_db: AsyncIOMotorDatabase = mongo_client[settings.mongo_db_name]

sessions_collection = _db["sessions"]

DEFAULT_SESSION_TITLE = "New conversation"
_TITLE_MAX_LEN = 60


def get_database() -> AsyncIOMotorDatabase:
    """Expose the raw database handle, e.g. for the LangGraph checkpointer."""
    return _db


async def create_session(thread_id: str, title: str | None) -> SessionDocument:
    """Insert a new session document and return it."""
    now = datetime.now(UTC)
    session = SessionDocument(
        id=thread_id, title=title or DEFAULT_SESSION_TITLE, created_at=now, updated_at=now
    )
    await sessions_collection.insert_one(session.model_dump(by_alias=True))
    return session


async def list_sessions() -> list[SessionDocument]:
    """Return all sessions, most recently updated first, for the sidebar."""
    cursor = sessions_collection.find().sort("updated_at", -1)
    return [SessionDocument.model_validate(doc) async for doc in cursor]


async def get_session(thread_id: str) -> SessionDocument | None:
    doc = await sessions_collection.find_one({"_id": thread_id})
    return SessionDocument.model_validate(doc) if doc else None


async def touch_session(thread_id: str) -> None:
    """Bump `updated_at` whenever a new message is sent in a session, so the
    sidebar's "most recent" ordering stays accurate."""
    await sessions_collection.update_one(
        {"_id": thread_id},
        {"$set": {"updated_at": datetime.now(UTC)}},
    )


async def set_title_from_first_message(thread_id: str, message: str) -> None:
    """Rename a session from the generic default to something recognizable,
    using the user's first message - only on the first message. The filter
    on `title: DEFAULT_SESSION_TITLE` in the query means this is a no-op on
    every later message in the same conversation.
    """
    title = message.strip().replace("\n", " ")
    if not title:
        return
    if len(title) > _TITLE_MAX_LEN:
        title = title[: _TITLE_MAX_LEN - 1].rstrip() + "…"

    await sessions_collection.update_one(
        {"_id": thread_id, "title": DEFAULT_SESSION_TITLE},
        {"$set": {"title": title}},
    )


async def delete_session(thread_id: str) -> bool:
    """Delete the session metadata document. The caller is responsible for
    also clearing the corresponding LangGraph checkpoints (see api/sessions.py)."""
    result = await sessions_collection.delete_one({"_id": thread_id})
    return result.deleted_count > 0
