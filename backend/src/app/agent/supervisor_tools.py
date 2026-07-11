"""Tools that let the supervisor (`graph.py`'s `agent_node`) delegate to a
specialist sub-agent.

Each tool here wraps one compiled specialist graph (e.g. `weather_agent`)
and exposes it to the supervisor as a single callable tool, same as
`agent/tools.py`'s `multiply` - the supervisor doesn't know or care that a
whole sub-agent ran underneath; it just sees a tool that returns text. This
is what makes `tools_node`'s existing "loop over every tool call in this
turn" logic handle multi-specialist requests (e.g. "what's the weather AND
what's 6 times 7") with no new control flow.
"""

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

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


SUPERVISOR_TOOLS = [weather_agent_tool]
