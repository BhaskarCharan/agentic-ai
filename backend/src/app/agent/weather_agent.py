"""The weather specialist - a small prebuilt ReAct agent the supervisor
calls as a tool (see `supervisor_tools.py`).

This is the first place a prebuilt agent constructor gets used in this
codebase, deliberately: the top-level supervisor's agent/tools loop is
hand-rolled in `graph.py` to teach the primitives, but a *specialist*
sub-agent isn't the thing being taught here - the point of this phase is
the supervisor/specialist coordination pattern, so the specialist itself
can lean on the prebuilt.

Uses `langchain.agents.create_agent` rather than the older
`langgraph.prebuilt.create_react_agent` - the latter is deprecated as of
LangGraph 1.0 in favor of this one (confirmed via a live deprecation
warning on the installed `langgraph==1.2.9`).
"""

from langchain.agents import create_agent

from app.agent.llm import get_llm
from app.agent.weather_tools import WEATHER_TOOLS

# No checkpointer here - this sub-agent's internal reasoning doesn't need
# its own persisted history; only the top-level supervisor's conversation
# does (via the MongoDBSaver in graph.py's build_graph()).
weather_agent = create_agent(get_llm(), WEATHER_TOOLS, name="weather_agent")
