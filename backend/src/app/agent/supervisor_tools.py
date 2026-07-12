"""Tools that let the supervisor (`graph.py`'s `agent_node`) delegate to a
specialist sub-agent.

Each tool here wraps one compiled specialist graph (e.g. `weather_agent`)
and exposes it to the supervisor as a single callable tool, same as
`agent/tools.py`'s `multiply` - the supervisor doesn't know or care that a
whole sub-agent ran underneath; it just sees a tool that returns text. This
is what makes `tools_node`'s existing "loop over every tool call in this
turn" logic handle multi-specialist requests (e.g. "what's the weather AND
what's 6 times 7") with no new control flow.

The Gmail/LinkedIn wrappers catch broadly around their sub-agent's
`ainvoke()` - confirmed live that a disconnected/expired Composio
connection raises a raw `composio_client.BadRequestError` from deep inside
the sub-agent's own tool execution, which is NOT absorbed by
`create_agent()`'s default error handling - it propagates all the way
through `tools_node`'s `interrupt()`-based flow and crashes the entire
supervisor turn, not just this one tool call. There's no way to enumerate
every failure mode a third-party API can produce (expired token, revoked
scope, rate limit, an outage), so this is a deliberate, documented
exception to "don't catch broadly": the alternative is the whole
conversation turn dying instead of the model getting an actionable message
it can relay to the user.
"""

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.agent.gmail_agent import get_gmail_agent
from app.agent.linkedin_agent import get_linkedin_agent
from app.agent.messages import extract_text
from app.agent.weather_agent import weather_agent


@tool
async def weather_agent_tool(request: str) -> str:
    """Delegate a weather-related question to the weather specialist agent.
    Pass the user's weather question as-is, e.g. "what's the weather in
    Hyderabad today?".
    """
    result = await weather_agent.ainvoke({"messages": [HumanMessage(content=request)]})
    return extract_text(result["messages"][-1].content)


@tool
async def gmail_agent_tool(request: str) -> str:
    """Delegate a Gmail-related question (reading, searching, or
    summarizing email) to the Gmail specialist agent. Pass the user's
    request as-is, e.g. "read my latest email and summarize it". Read-only
    - it cannot send, delete, or modify anything.
    """
    try:
        result = await get_gmail_agent().ainvoke({"messages": [HumanMessage(content=request)]})
    except Exception:
        return (
            "I couldn't reach Gmail just now - the connected account may not "
            "be linked, or its session may have expired. Check the "
            "'Connected accounts' panel in the sidebar and reconnect if "
            "needed."
        )
    return extract_text(result["messages"][-1].content)


@tool
async def linkedin_agent_tool(request: str) -> str:
    """Delegate a LinkedIn-related question (the user's own profile, or
    looking up a person/company) to the LinkedIn specialist agent. Pass the
    user's request as-is, e.g. "what's my LinkedIn headline?". Read-only -
    it cannot post, comment, or delete anything.
    """
    try:
        result = await get_linkedin_agent().ainvoke({"messages": [HumanMessage(content=request)]})
    except Exception:
        return (
            "I couldn't reach LinkedIn just now - the connected account may "
            "not be linked, or its session may have expired. Check the "
            "'Connected accounts' panel in the sidebar and reconnect if "
            "needed."
        )
    return extract_text(result["messages"][-1].content)


SUPERVISOR_TOOLS = [weather_agent_tool, gmail_agent_tool, linkedin_agent_tool]
