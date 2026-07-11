"""SSE chat endpoints - the Controller layer.

Routes only do HTTP/SSE-shaped work: check the session exists, call
`SessionService` for the metadata side-effects (touch/rename), and format
`AgentService`'s `(event_type, payload)` events as SSE wire-format strings.
Driving the LangGraph graph itself - `astream`, `interrupt()` payloads,
`Command(resume=...)` - lives in `app/services/agent_service.py`, not here.

  * POST /chat   -> AgentService.start_turn (a brand-new turn)
  * POST /resume -> AgentService.resume_turn (continuing a turn that paused
                    on an `interrupt()` inside `tools_node`)

Three SSE event types are emitted, one per `AgentEvent` from the service:
  * "token"     - a chunk of the AI's streamed text response
  * "interrupt" - the graph paused before running a tool; payload describes
                  which tool/args are pending, frontend should ask the user
  * "done"      - the graph reached END for this turn
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import AgentServiceDep, SessionServiceDep
from app.api.schemas import ChatMessageIn, ResumeRequest
from app.services.agent_service import AgentEvent

router = APIRouter(prefix="/api/sessions", tags=["chat"])

# Headers that discourage any intermediary (dev proxy, browser) from
# buffering the response, which would defeat the point of streaming.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event line per the SSE wire format."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _to_sse(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """Adapt the service's transport-agnostic events to SSE wire format -
    the only part of this file that knows what "SSE" even means."""
    async for event_type, payload in events:
        yield _sse(event_type, payload)


@router.post("/{thread_id}/chat")
async def chat(
    thread_id: str, body: ChatMessageIn, sessions: SessionServiceDep, agent: AgentServiceDep
):
    if await sessions.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await sessions.touch_session(thread_id)
    await sessions.set_title_from_first_message(thread_id, body.message)

    return StreamingResponse(
        _to_sse(agent.start_turn(thread_id, body.message)),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{thread_id}/resume")
async def resume(
    thread_id: str, body: ResumeRequest, sessions: SessionServiceDep, agent: AgentServiceDep
):
    if await sessions.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return StreamingResponse(
        _to_sse(agent.resume_turn(thread_id, body.approved)),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
