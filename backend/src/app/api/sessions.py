"""Session (conversation) management routes - the Controller layer.

A "session" is one conversation thread. Its `id` doubles as the LangGraph
`thread_id` used to key checkpoints, so listing/loading/deleting a session
here also means listing/loading/deleting the matching agent state.

Routes only translate HTTP <-> service calls; no Mongo query, business rule,
or graph interaction lives in this file - session metadata rules are in
`app/services/session_service.py`, graph/checkpoint access is in
`app/services/agent_service.py`.
"""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import AgentServiceDep, SessionServiceDep
from app.api.schemas import CreateSessionRequest, MessageOut, SessionOut

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut)
async def create_session(body: CreateSessionRequest, service: SessionServiceDep):
    session = await service.create_session(body.title)
    return SessionOut(**session.model_dump())


@router.get("", response_model=list[SessionOut])
async def list_sessions(service: SessionServiceDep):
    sessions = await service.list_sessions()
    return [SessionOut(**s.model_dump()) for s in sessions]


@router.get("/{thread_id}/history", response_model=list[MessageOut])
async def get_history(thread_id: str, sessions: SessionServiceDep, agent: AgentServiceDep):
    if await sessions.get_session(thread_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    history = await agent.get_history(thread_id)
    return [MessageOut(role=m.role, content=m.content) for m in history]


@router.delete("/{thread_id}", status_code=204)
async def delete_session(thread_id: str, sessions: SessionServiceDep, agent: AgentServiceDep):
    if not await sessions.delete_session(thread_id):
        raise HTTPException(status_code=404, detail="Session not found")

    await agent.delete_thread(thread_id)
