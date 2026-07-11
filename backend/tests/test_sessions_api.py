"""Smoke tests for session CRUD - deliberately don't touch /chat or /resume
since those call the real Gemini API, which needs a real GOOGLE_API_KEY.
"""

from app.db import get_database


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_list_delete_session(client):
    create_resp = await client.post("/api/sessions", json={"title": "Test chat"})
    assert create_resp.status_code == 200
    session = create_resp.json()
    assert session["title"] == "Test chat"

    list_resp = await client.get("/api/sessions")
    assert list_resp.status_code == 200
    assert any(s["id"] == session["id"] for s in list_resp.json())

    history_resp = await client.get(f"/api/sessions/{session['id']}/history")
    assert history_resp.status_code == 200
    assert history_resp.json() == []  # no messages sent yet

    delete_resp = await client.delete(f"/api/sessions/{session['id']}")
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/api/sessions/{session['id']}/history")
    assert missing_resp.status_code == 404


async def test_default_title_when_omitted(client):
    resp = await client.post("/api/sessions", json={})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New conversation"


async def test_delete_cascades_to_checkpoints_and_writes(client):
    """DELETE /api/sessions/{id} must also clear LangGraph's checkpoint
    collections for that thread - otherwise a "deleted" chat would still
    reappear the moment you asked it a new question with the same id. We
    seed minimal fake documents instead of driving a real graph run, since
    that would need a live LLM call.
    """
    create_resp = await client.post("/api/sessions", json={})
    thread_id = create_resp.json()["id"]

    db = get_database()
    await db["checkpoints"].insert_one(
        {
            "thread_id": thread_id,
            "checkpoint_ns": "",
            "checkpoint_id": "fake-checkpoint",
            "parent_checkpoint_id": None,
            "type": "msgpack",
            "checkpoint": b"",
            "metadata": b"",
        }
    )
    await db["checkpoint_writes"].insert_one(
        {
            "thread_id": thread_id,
            "checkpoint_ns": "",
            "checkpoint_id": "fake-checkpoint",
            "task_id": "fake-task",
            "task_path": "",
            "idx": 0,
            "channel": "messages",
            "type": "msgpack",
            "value": b"",
        }
    )

    delete_resp = await client.delete(f"/api/sessions/{thread_id}")
    assert delete_resp.status_code == 204

    assert await db["checkpoints"].count_documents({"thread_id": thread_id}) == 0
    assert await db["checkpoint_writes"].count_documents({"thread_id": thread_id}) == 0
