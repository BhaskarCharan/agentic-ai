"""Data access for the `sessions` collection - the Repository pattern.

A repository's only job is translating between "the database" and typed
domain objects (`SessionDocument`). It knows Mongo query syntax; it does NOT
know about business rules like "what's the default title" or "only rename
on the first message" - that belongs one layer up, in
`app/services/session_service.py`. This separation is what lets the service
layer be unit-tested against a fake repository with no real MongoDB
involved, and what lets the storage engine change without touching business
logic.
"""

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.session import SessionDocument


class SessionRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database["sessions"]

    async def insert(self, session: SessionDocument) -> None:
        await self._collection.insert_one(session.model_dump(by_alias=True))

    async def find_all(self) -> list[SessionDocument]:
        """Most recently updated first, for the sidebar."""
        cursor = self._collection.find().sort("updated_at", -1)
        return [SessionDocument.model_validate(doc) async for doc in cursor]

    async def find_by_id(self, thread_id: str) -> SessionDocument | None:
        doc = await self._collection.find_one({"_id": thread_id})
        return SessionDocument.model_validate(doc) if doc else None

    async def update_timestamp(self, thread_id: str, updated_at: datetime) -> None:
        await self._collection.update_one(
            {"_id": thread_id},
            {"$set": {"updated_at": updated_at}},
        )

    async def update_title_if_matches(
        self, thread_id: str, current_title: str, new_title: str
    ) -> None:
        """Set `title` only if it still equals `current_title`. Used to rename
        a session exactly once, from the default title to something
        recognizable - a no-op on every later call for the same thread."""
        await self._collection.update_one(
            {"_id": thread_id, "title": current_title},
            {"$set": {"title": new_title}},
        )

    async def delete(self, thread_id: str) -> bool:
        result = await self._collection.delete_one({"_id": thread_id})
        return result.deleted_count > 0
