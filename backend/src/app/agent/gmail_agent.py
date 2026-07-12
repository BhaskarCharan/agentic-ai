"""The Gmail specialist - a small prebuilt agent the supervisor calls as a
tool (see `supervisor_tools.py`). Same reasoning as `weather_agent.py` for
why `create_agent` is the right choice for a specialist sub-agent - see
that file's docstring.

Unlike `weather_agent.py`'s module-level `weather_agent` constant,
`get_gmail_agent()` is built lazily and cached rather than constructed at
import time: `get_gmail_tools()` makes a live Composio API call, and
importing `agent.graph` (which pulls this in transitively) must not
require a working Composio connection just to import a module - the test
suite, in particular, never configures `COMPOSIO_API_KEY`.
"""

from functools import lru_cache

from langchain.agents import create_agent

from app.agent.gmail_tools import get_gmail_tools
from app.agent.llm import get_llm


@lru_cache
def get_gmail_agent():
    return create_agent(get_llm(), get_gmail_tools(), name="gmail_agent")
