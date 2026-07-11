"""SSE chat endpoints.

Both routes below stream a `text/event-stream` response built from the same
underlying generator, `_stream_graph`. The only difference between them is
what they feed into the graph to kick off/continue execution:

  * POST /chat   -> a brand-new HumanMessage (start of a normal turn)
  * POST /resume -> a `Command(resume=...)` (continuing a turn that paused
                    on an `interrupt()` inside `tools_node`)

Three SSE event types are emitted:
  * "token"     - a chunk of the AI's streamed text response
  * "interrupt" - the graph paused before running a tool; payload describes
                  which tool/args are pending, frontend should ask the user
  * "done"      - the graph reached END for this turn
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from app import db
from app.agent.messages import extract_text
from app.api.schemas import ChatMessageIn, ResumeRequest

router = APIRouter(prefix="/api/sessions", tags=["chat"])

# Headers that discourage any intermediary (dev proxy, browser) from
# buffering the response, which would defeat the point of streaming.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event line per the SSE wire format."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_graph(graph, config: dict, graph_input) -> AsyncIterator[str]:
    """Drive the graph and translate its events into SSE-formatted strings.

    `stream_mode=["messages", "updates"]` asks LangGraph for two interleaved
    streams at once: "messages" gives us token-by-token LLM output chunks,
    "updates" gives us node-level state diffs - which is where a paused
    `interrupt()` shows up, as a special "__interrupt__" key.
    """
    stream_modes = ["messages", "updates"]
    async for mode, event in graph.astream(graph_input, config, stream_mode=stream_modes):
        if mode == "messages":
            message_chunk, _metadata = event
            # `tools_node`'s ToolMessage also comes through the "messages"
            # stream (as one complete message, not token-by-token) - skip
            # it, the frontend should only ever see the AI's own words.
            if isinstance(message_chunk, ToolMessage):
                continue
            text = extract_text(message_chunk.content)
            if text:
                yield _sse("token", {"content": text})

        elif mode == "updates" and "__interrupt__" in event:
            pending = event["__interrupt__"][0]
            yield _sse("interrupt", pending.value)
            # The graph is now paused waiting on /resume - nothing more will
            # come from this stream until that happens, so stop here.
            return

    yield _sse("done", {})


@router.post("/{thread_id}/chat")
async def chat(thread_id: str, body: ChatMessageIn, request: Request):
    if await db.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.touch_session(thread_id)
    await db.set_title_from_first_message(thread_id, body.message)

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {"messages": [HumanMessage(content=body.message)]}

    return StreamingResponse(
        _stream_graph(graph, config, graph_input),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{thread_id}/resume")
async def resume(thread_id: str, body: ResumeRequest, request: Request):
    if await db.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = Command(resume=body.approved)

    return StreamingResponse(
        _stream_graph(graph, config, graph_input),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
