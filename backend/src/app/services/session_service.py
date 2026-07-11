"""Business logic for sessions - the Service Layer pattern.

Everything here is a *rule*, not a query: what a new session's default title
is, how a title gets truncated, that a thread_id is a fresh UUID. The
service depends on a `SessionRepository` for actual persistence but never
touches Mongo query syntax itself - that keeps this layer testable with a
fake/in-memory repository and reusable across every controller that needs
session behaviour (`api/sessions.py` and `api/chat.py` both go through this
one class instead of duplicating the rules).
"""

import uuid
from datetime import UTC, datetime

from app.models.session import SessionDocument
from app.repositories.session_repository import SessionRepository

DEFAULT_SESSION_TITLE = "New conversation"
_TITLE_MAX_LEN = 60


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    async def create_session(self, title: str | None) -> SessionDocument:
        now = datetime.now(UTC)
        session = SessionDocument(
            id=str(uuid.uuid4()),
            title=title or DEFAULT_SESSION_TITLE,
            created_at=now,
            updated_at=now,
        )
        await self._repository.insert(session)
        return session

    async def list_sessions(self) -> list[SessionDocument]:
        return await self._repository.find_all()

    async def get_session(self, thread_id: str) -> SessionDocument | None:
        return await self._repository.find_by_id(thread_id)

    async def touch_session(self, thread_id: str) -> None:
        """Bump `updated_at` whenever a new message is sent in a session, so
        the sidebar's "most recent" ordering stays accurate."""
        await self._repository.update_timestamp(thread_id, datetime.now(UTC))

    async def set_title_from_first_message(self, thread_id: str, message: str) -> None:
        """Rename a session from the generic default to something
        recognizable, using the user's first message - only on the first
        message. `update_title_if_matches` guards on the current title still
        being the default, so this is a no-op on every later message in the
        same conversation.
        """
        title = message.strip().replace("\n", " ")
        if not title:
            return
        if len(title) > _TITLE_MAX_LEN:
            title = title[: _TITLE_MAX_LEN - 1].rstrip() + "…"

        await self._repository.update_title_if_matches(thread_id, DEFAULT_SESSION_TITLE, title)

    async def delete_session(self, thread_id: str) -> bool:
        """Delete the session metadata document. The caller is responsible
        for also clearing the corresponding LangGraph checkpoints (see
        api/sessions.py)."""
        return await self._repository.delete(thread_id)
