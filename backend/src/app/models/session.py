"""The `sessions` collection - ours (as opposed to LangGraph-owned; see
`models/checkpoint.py`).

One document per conversation. Pure UI-facing metadata - it exists only so
the frontend can render a sidebar of past conversations without asking
LangGraph "list me every thread_id you know about" (which its checkpointer
doesn't support). The actual message content is never stored here; it lives
in `checkpoints`, keyed by this same id.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Doubles as the LangGraph `thread_id` - deleting a session by this id
    # also means deleting the checkpoints filed under the same thread_id.
    id: str = Field(alias="_id")
    title: str
    created_at: datetime
    updated_at: datetime
