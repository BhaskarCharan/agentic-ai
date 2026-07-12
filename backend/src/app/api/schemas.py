"""Pydantic request/response models for the HTTP API.

Keeping these separate from the LangGraph state (app/agent/graph.py) is
deliberate: the API's shape is a stable contract with the frontend, while
the graph's internal message format is free to evolve independently.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    # Optional custom title; falls back to a generic one if omitted.
    title: str | None = None


class ChatMessageIn(BaseModel):
    message: str


class ResumeRequest(BaseModel):
    # True = go ahead and run the tool, False = cancel this tool call.
    approved: bool


class MessageOut(BaseModel):
    # Tool messages are filtered out before they ever reach this model - see
    # api/sessions.py:get_history and api/chat.py:_stream_graph.
    role: Literal["human", "ai"]
    content: str


class IntegrationStatusOut(BaseModel):
    toolkit: str
    connected: bool
    connected_since: str | None = None
    # Human-readable identity (email for Gmail, name for LinkedIn) - best
    # effort, may be None even when connected (see IntegrationService).
    label: str | None = None


class ConnectResponse(BaseModel):
    # The frontend sends the user's browser here to complete OAuth consent.
    redirect_url: str
