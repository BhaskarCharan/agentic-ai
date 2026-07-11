"""Session (conversation) management routes.

A "session" is one conversation thread. Its `id` doubles as the LangGraph
`thread_id` used to key checkpoints, so listing/loading/deleting a session
here also means listing/loading/deleting the matching agent state.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app import db
from app.agent.messages import extract_text
from app.api.schemas import CreateSessionRequest, MessageOut, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut)
async def create_session(body: CreateSessionRequest):
    thread_id = str(uuid.uuid4())
    session = await db.create_session(thread_id, body.title)
    return SessionOut(**session.model_dump())


@router.get("", response_model=list[SessionOut])
async def list_sessions():
    sessions = await db.list_sessions()
    return [SessionOut(**s.model_dump()) for s in sessions]


@router.get("/{thread_id}/history", response_model=list[MessageOut])
async def get_history(thread_id: str, request: Request):
    """Replay the full message history for a session straight out of the
    LangGraph checkpointer - this is why we don't need our own messages
    collection at all."""
    if await db.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)

    messages = snapshot.values.get("messages", []) if snapshot.values else []
    out = []
    for m in messages:
        # Tool messages are internal plumbing (the raw `multiply` result) -
        # the frontend should only ever show what the human said and what
        # the AI said in response, never the tool's raw output.
        if m.type not in ("human", "ai"):
            continue
        text = extract_text(m.content)
        # Tool-confirmation plumbing also produces empty-content AI messages
        # (the ones that only carry a tool_call) - skip those too.
        if text:
            out.append(MessageOut(role=m.type, content=text))
    return out


@router.delete("/{thread_id}", status_code=204)
async def delete_session(thread_id: str, request: Request):
    if not await db.delete_session(thread_id):
        raise HTTPException(status_code=404, detail="Session not found")

    graph = request.app.state.graph
    await graph.checkpointer.adelete_thread(thread_id)
