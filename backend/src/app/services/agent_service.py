"""Business logic for driving the agent graph - the Service layer for chat
turns, history, and thread deletion.

This is where LangGraph specifics live: `astream`/`stream_mode`, `Command`,
filtering `ToolMessage` out of the token stream, unpacking `interrupt()`
payloads, replaying state via `aget_state()`. Controllers (`api/chat.py`,
`api/sessions.py`) never touch the graph directly - they only see plain
`(event_type, payload)` tuples or `HistoryMessage`s, and format those into
HTTP/SSE. That split is what makes it possible to unit-test this class
against a fake compiled graph, with no FastAPI request/response involved.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.agent.messages import extract_text

# event_type is one of "token" | "interrupt" | "done" - see `_stream` below.
AgentEvent = tuple[str, dict[str, Any]]


@dataclass
class HistoryMessage:
    role: str  # "human" | "ai"
    content: str


class AgentService:
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def start_turn(self, thread_id: str, message: str) -> AsyncIterator[AgentEvent]:
        """Kick off a brand-new turn with the user's message."""
        graph_input = {"messages": [HumanMessage(content=message)]}
        async for event in self._stream(thread_id, graph_input):
            yield event

    async def resume_turn(self, thread_id: str, approved: bool) -> AsyncIterator[AgentEvent]:
        """Continue a turn that paused on an `interrupt()` inside `tools_node`."""
        async for event in self._stream(thread_id, Command(resume=approved)):
            yield event

    async def _stream(self, thread_id: str, graph_input: Any) -> AsyncIterator[AgentEvent]:
        """Drive the graph and translate its raw events into
        `(event_type, payload)` pairs.

        `stream_mode=["messages", "updates"]` asks LangGraph for two
        interleaved streams at once: "messages" gives us token-by-token LLM
        output chunks, "updates" gives us node-level state diffs - which is
        where a paused `interrupt()` shows up, as a special "__interrupt__"
        key.
        """
        config = {"configurable": {"thread_id": thread_id}}
        async for mode, event in self._graph.astream(
            graph_input, config, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                message_chunk, _metadata = event
                # `tools_node`'s ToolMessage also comes through the
                # "messages" stream (as one complete message, not
                # token-by-token) - skip it, callers should only ever see
                # the AI's own words.
                if isinstance(message_chunk, ToolMessage):
                    continue
                text = extract_text(message_chunk.content)
                if text:
                    yield ("token", {"content": text})

            elif mode == "updates" and "__interrupt__" in event:
                pending = event["__interrupt__"][0]
                yield ("interrupt", pending.value)
                # The graph is now paused waiting on a resume - nothing more
                # will come from this stream until that happens.
                return

        yield ("done", {})

    async def get_history(self, thread_id: str) -> list[HistoryMessage]:
        """Replay the full message history for a thread straight out of the
        LangGraph checkpointer - this is why there's no separate messages
        collection at all."""
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = await self._graph.aget_state(config)

        messages = snapshot.values.get("messages", []) if snapshot.values else []
        out = []
        for m in messages:
            # Tool messages are internal plumbing (the raw `multiply`
            # result) - callers should only ever see what the human said
            # and what the AI said in response.
            if m.type not in ("human", "ai"):
                continue
            text = extract_text(m.content)
            # Tool-confirmation plumbing also produces empty-content AI
            # messages (the ones that only carry a tool_call) - skip those
            # too.
            if text:
                out.append(HistoryMessage(role=m.type, content=text))
        return out

    async def delete_thread(self, thread_id: str) -> None:
        """Delete all LangGraph checkpoints/writes for a thread - the agent
        half of "delete a session" (see `SessionService` for the metadata
        half, in `api/sessions.py`)."""
        await self._graph.checkpointer.adelete_thread(thread_id)
