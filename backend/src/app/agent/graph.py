"""
The agent itself: a small LangGraph graph with two nodes.

    START -> agent -> (tool call?) -> tools -> agent -> ... -> END

  * "agent"  - calls the LLM (with `multiply` bound as a tool). The LLM
              either answers directly (-> END) or asks to call a tool
              (-> "tools").
  * "tools"  - before actually running a requested tool, this node calls
              LangGraph's `interrupt()`, which PAUSES the whole graph run
              and hands control back to our FastAPI layer with a payload
              describing the pending call. The API surfaces that to the
              frontend as an "awaiting confirmation" SSE event. Once the
              user approves/declines (via POST /resume), FastAPI resumes
              this exact node with `Command(resume=<bool>)`, and only then
              do we actually invoke the tool (or record a cancellation).

This "confirm before every tool call" behaviour is what the task calls an
"interrupt" - it's LangGraph's built-in human-in-the-loop mechanism, not
something we hand-rolled.

Persistence ("checkpoints") comes from compiling the graph with a
`checkpointer`: LangGraph automatically saves the full state (message
history + where execution paused) after every node, keyed by a `thread_id`.
That's what lets a conversation survive a server restart, and what makes
resuming an interrupted run possible in the first place - the checkpointer
is *how* the paused state is remembered between the interrupt and the
resume, which may be two entirely separate HTTP requests.
"""

import pymongo
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import tools_condition
from langgraph.types import interrupt

from app.agent.llm import get_llm
from app.agent.tools import TOOLS
from app.config import settings

# Map of tool name -> callable, so the "tools" node can look up the right
# tool to invoke once the human has approved a pending call.
_TOOLS_BY_NAME = {t.name: t for t in TOOLS}

# The LLM with `multiply` bound as a callable tool. Binding tools doesn't
# execute anything - it just tells the model "here's a function you can ask
# to have called, and here's its schema"; the model responds with a
# tool_calls list on its AIMessage when it wants to use one.
_llm_with_tools = get_llm().bind_tools(TOOLS)

# Without this, some models (Gemini included) sometimes answer a tool
# result with just the bare number ("400.0") instead of a sentence - because
# nothing ever told them not to. This is prepended on every agent turn, not
# stored in the persisted history, since it's a standing instruction rather
# than part of the conversation.
_SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a helpful assistant with access to a `multiply` tool. "
        "After a tool call returns a result, always reply with a complete, "
        "friendly sentence stating the answer in context - never reply with "
        "just the bare number on its own."
    )
)


def agent_node(state: MessagesState) -> dict:
    """Ask the LLM what to do next, given the conversation so far."""
    response = _llm_with_tools.invoke([_SYSTEM_PROMPT, *state["messages"]])
    return {"messages": [response]}


def tools_node(state: MessagesState) -> dict:
    """Confirm with the human, then execute (or skip) each requested tool call.

    NOTE on `interrupt()` semantics: when this node is resumed after a pause,
    LangGraph re-runs the node function from the top. Any `interrupt()` call
    that already has a resume value replays that value instantly instead of
    pausing again, so this loop safely "continues" past tool calls that were
    already confirmed earlier in the same node execution.
    """
    last_message = state["messages"][-1]
    results: list[ToolMessage] = []

    for call in last_message.tool_calls:
        approved = interrupt(
            {
                "type": "tool_confirmation",
                "tool_name": call["name"],
                "tool_args": call["args"],
            }
        )

        if approved:
            tool = _TOOLS_BY_NAME[call["name"]]
            output = tool.invoke(call["args"])
            content = str(output)
        else:
            content = f"The user declined to run `{call['name']}`."

        results.append(ToolMessage(content=content, tool_call_id=call["id"], name=call["name"]))

    return {"messages": results}


def build_graph() -> CompiledStateGraph:
    """Wire the nodes/edges together and compile with a MongoDB checkpointer.

    Called once, at application startup (see main.py's lifespan), so the
    Mongo connection used for checkpointing is created a single time and
    shared for the life of the process.

    Note: `MongoDBSaver` takes a *synchronous* pymongo client even though it
    exposes async methods (`aget_tuple`, `aput`, ...) - those wrap the sync
    driver calls internally. This is a separate connection from the Motor
    client in app/db.py, which is only used for our own `sessions` metadata.
    """
    checkpointer = MongoDBSaver(
        pymongo.MongoClient(settings.mongo_uri),
        db_name=settings.mongo_db_name,
    )

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "agent")
    # `tools_condition` inspects the last AIMessage: if it has tool_calls,
    # route to "tools", otherwise the model gave a final answer -> END.
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)
