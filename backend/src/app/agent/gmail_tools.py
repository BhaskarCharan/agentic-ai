"""Read-only Gmail tools for the Gmail specialist agent (see
`gmail_agent.py`) - fetched from Composio, not hand-written `@tool`
functions like `weather_tools.py`, since Composio's LangChain provider
already returns ready-to-bind `BaseTool` objects with rich, real schemas
(verified live before writing this).

Deliberately read-only: Gmail exposes 60+ actions on Composio, many
destructive (`GMAIL_DELETE_MESSAGE`, `GMAIL_BATCH_DELETE_MESSAGES`) or
externally-visible writes (`GMAIL_SEND_EMAIL`, `GMAIL_REPLY_TO_THREAD`).
Unlike the top-level supervisor's `tools_node` (which pauses on every call
via `interrupt()`), a specialist sub-agent built with `create_agent()` has
no human-in-the-loop gate at all on its own internal tool calls - binding a
send/delete action here would let the model act on the user's real inbox
with zero approval. Widen this list only once Phase 4 gives specialist
sub-agents their own approval gate for sensitive actions.
"""

from app.composio_client import get_composio_langchain_client
from app.config import settings

# Enough to "read the latest email and summarize it" (Phase 2's stated
# goal in MULTI_AGENT_ROADMAP.md) plus general search/thread-reading.
_GMAIL_TOOL_NAMES = [
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
]


def get_gmail_tools() -> list:
    """Fetch this app's fixed set of read-only Gmail tools, scoped to the
    one account this app knows about (`settings.composio_user_id`).

    Fetching tool *schemas* doesn't require a live connection - only
    actually calling one does (confirmed live: this succeeds regardless of
    connection status, and only the model's attempt to *use* a tool fails
    if Gmail isn't connected via Phase 1's integrations panel).
    """
    client = get_composio_langchain_client()
    return client.tools.get(user_id=settings.composio_user_id, tools=_GMAIL_TOOL_NAMES)
