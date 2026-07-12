"""Read-only LinkedIn tools for the LinkedIn specialist agent (see
`linkedin_agent.py`) - see `gmail_tools.py` for the full reasoning behind
fetching from Composio rather than hand-writing, and why this list is
deliberately read-only (LinkedIn's write actions -
`LINKEDIN_CREATE_LINKED_IN_POST`, `LINKEDIN_DELETE_POST`, etc. - have no
approval gate inside a `create_agent()` specialist yet).
"""

from app.composio_client import get_composio_langchain_client
from app.config import settings

# Enough for "what's my LinkedIn headline", profile/company lookups - the
# read-only core of Phase 3's stated goal in MULTI_AGENT_ROADMAP.md.
_LINKEDIN_TOOL_NAMES = [
    "LINKEDIN_GET_MY_INFO",
    "LINKEDIN_GET_PERSON",
    "LINKEDIN_GET_COMPANY_INFO",
]


def get_linkedin_tools() -> list:
    """See `gmail_tools.get_gmail_tools` - same reasoning throughout
    (schema fetching doesn't need a live connection, only tool calls do)."""
    client = get_composio_langchain_client()
    return client.tools.get(user_id=settings.composio_user_id, tools=_LINKEDIN_TOOL_NAMES)
