"""MongoDB client setup - shared infrastructure only.

This module owns the one Motor client for the process lifetime and exposes
it via `get_database()`. It does NOT know about collections, documents, or
business rules - that's `app/repositories/` (raw CRUD) and
`app/services/` (business logic) respectively. Keeping this file this thin
is what let `sessions`-specific code move into its own layer instead of
living here forever.

LangGraph's own MongoDB checkpointer (see agent/graph.py) manages its own
collections ("checkpoints", "checkpoint_writes") through a separate,
synchronous pymongo connection - this Motor client is only ever used for our
own `sessions` metadata.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

# A single shared client for the process lifetime. Motor's client is safe to
# share across requests/coroutines - it manages its own connection pool.
mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri)
_db: AsyncIOMotorDatabase = mongo_client[settings.mongo_db_name]


def get_database() -> AsyncIOMotorDatabase:
    """Expose the raw database handle, e.g. for the LangGraph checkpointer
    or a repository's constructor."""
    return _db
