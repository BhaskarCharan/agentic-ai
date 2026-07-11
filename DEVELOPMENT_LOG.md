# Development Log

Context for whoever (human or AI) picks this project up next. `README.md`
tells you how to run it; this file tells you why it's built the way it is,
what already went wrong once, and what's still rough around the edges.

## What this is

A minimal AI chat app to demonstrate an **agent backend** end-to-end:
persistent history, checkpoints, human-in-the-loop interrupts, and SSE
streaming to a simple frontend. The one tool the agent has is `multiply` -
deliberately trivial, since the point of the project was the plumbing
around a tool call, not the tool itself.

## Stack and why

| Piece | Choice | Why |
|---|---|---|
| Agent framework | LangGraph | "Interrupts" and "checkpoints" were requested by name - both are LangGraph-native concepts (`interrupt()`/`Command(resume=...)`, `BaseCheckpointSaver`), not something hand-rolled. |
| LLM | Gemini (`gemini-flash-latest`) via `langchain-google-genai` | User had a Google AI Studio key. `agent/llm.py` isolates this behind a `get_llm()` factory - swapping providers means editing one file. |
| DB | MongoDB | Requested explicitly; also happens to have an official LangGraph checkpointer package. |
| Backend | FastAPI + `uv` + `pyproject.toml` + `Makefile` | Requested explicitly. |
| Frontend | Angular (latest stable, standalone + signals) | Requested explicitly, "simple UI," backend was the focus. |

## Repo layout

```
backend/
  src/app/
    agent/graph.py      - the LangGraph graph (agent <-> tools, interrupt, checkpointer)
    agent/tools.py       - the multiply tool
    agent/llm.py          - swappable LLM factory
    agent/messages.py    - extract_text() - handles provider content-format quirks
    api/chat.py           - controller: SSE endpoints (/chat, /resume), formats SSE only
    api/sessions.py       - controller: session CRUD, history
    api/dependencies.py    - FastAPI Depends() wiring: database -> repository -> service
    services/session_service.py       - business rules (default title, rename-once, ...)
    services/agent_service.py          - all graph interaction (astream, interrupt/resume, aget_state, adelete_thread) - controllers never touch `graph` directly
    repositories/session_repository.py - raw Mongo CRUD for the `sessions` collection
    models/session.py                   - SessionDocument (ours)
    models/checkpoint.py                 - CheckpointDocument/CheckpointWriteDocument (reference only)
    db.py                  - Motor client + get_database() only, no collection code
    config.py              - pydantic-settings, reads .env
frontend/
  src/app/
    chat.service.ts       - owns chat state as signals, hand-parses the SSE stream
    api.service.ts         - plain CRUD for sessions
    sse.ts                  - manual SSE parser (fetch-based, not EventSource)
    app.ts/.html/.css      - sidebar + chat panel, single-component UI
DEVELOPMENT_LOG.md   - this file
README.md              - how to run it
```

## Architecture decisions worth knowing

- **Why not `EventSource` for streaming?** It can't send a POST body, and
  `/chat` needs to POST the user's message. The frontend reads the raw
  `fetch()` response stream and parses SSE (`event:`/`data:` lines) by hand
  in `sse.ts`.
- **Why a separate `sessions` collection instead of just using LangGraph's
  checkpoints for everything?** LangGraph's checkpointer has no "list all
  threads" API - it's keyed by `thread_id`, not discoverable. `sessions`
  exists purely so the sidebar has something to list and title.
- **Why `MongoDBSaver` and not `AsyncMongoDBSaver`?** The installed version
  of `langgraph-checkpoint-mongodb` (0.4.0) only ships `MongoDBSaver`, which
  exposes both sync and async methods on one class and takes a *synchronous*
  `pymongo.MongoClient`. Earlier LangGraph docs/tutorials reference a
  separate async class that doesn't exist in this version - don't reintroduce
  it without checking `pip show`/the installed source first.
- **Why does `agent_node` prepend a `SystemMessage` on every call instead of
  storing it in history?** It's a standing instruction ("always answer tool
  results in a full sentence"), not part of the conversation - storing it
  in the checkpointed message list would mean it shows up in `/history` too.
- **Why filter by `isinstance(message_chunk, ToolMessage)` instead of by
  `.type` string?** LangGraph's `stream_mode="messages"` emits *both*
  streamed AI token chunks and complete non-LLM messages (like
  `ToolMessage`) through the same channel. Checking the class directly
  side-steps any inconsistency in `.type` string values between message and
  chunk classes.
- **Why split `sessions` code into `models/` + `repositories/` +
  `services/` instead of one `db.py`?** `db.py` originally held Mongo
  queries, business rules (default title, rename-once-on-first-message),
  and the client setup all in one file. As more collections/agents get
  added, that file would keep growing and mixing concerns. Now: `db.py` is
  just the Motor client; `repositories/session_repository.py` is CRUD-only
  (knows Mongo, not "what a default title is"); `services/session_service.py`
  is business rules only (knows "what a default title is", not Mongo query
  syntax); `api/dependencies.py` wires them together via FastAPI's
  `Depends()` chain (`get_database -> get_session_repository ->
  get_session_service`). Controllers (`api/sessions.py`, `api/chat.py`)
  depend on `SessionService` only - this is the standard Repository +
  Service Layer layering, and the DI wiring is what makes each layer
  swappable/mockable later (e.g. a fake repository in a unit test, without
  a real MongoDB).
- **Why does `AgentService` exist separately from `SessionService`?** The
  first pass of this refactor moved Mongo/`sessions` logic out of `db.py`
  but left `api/chat.py` and `api/sessions.py` calling
  `graph.astream(...)`, `graph.aget_state(...)`, and
  `graph.checkpointer.adelete_thread(...)` directly - i.e. business logic
  (how to drive the LangGraph graph) was still sitting in the controller
  layer, just a different flavor of the same mistake `db.py` had. Moved
  into `app/services/agent_service.py`: it owns everything LangGraph-shaped
  (stream modes, `Command(resume=...)`, filtering `ToolMessage`, unpacking
  `interrupt()` payloads) and exposes plain, transport-agnostic types -
  `(event_type, payload)` tuples for streaming, `HistoryMessage` for
  history. `api/chat.py` now only formats those events as SSE wire format;
  it does not know what a `stream_mode` is. Wired into `Depends()` the same
  way as `SessionService`, via `get_graph` (reads `request.app.state.graph`
  - the one exception where a dependency factory needs the `Request`
  object) and `get_agent_service` in `api/dependencies.py`.

## MongoDB collections

Documented in detail with real field-level comments in `db_models.py`;
short version:

- **`sessions`** (ours) - `{_id: thread_id, title, created_at, updated_at}`.
  UI metadata only, no message content.
- **`checkpoints`** (LangGraph-owned) - one full state snapshot per graph
  step, chained via `parent_checkpoint_id`. Opaque msgpack blobs - never
  parsed by our code directly.
- **`checkpoint_writes`** (LangGraph-owned) - granular per-channel writes
  within a step. This is where the interrupt/resume mechanism is physically
  recorded: a `channel="__interrupt__"` write is the paused tool-call
  payload, `channel="__resume__"` is the approve/decline value.

Deleting a session cascades correctly: `DELETE /api/sessions/{id}` calls
both `db.delete_session()` (removes the `sessions` doc) and
`graph.checkpointer.adelete_thread()` (removes matching docs from both
`checkpoints` and `checkpoint_writes`) - verified live and covered by
`test_delete_cascades_to_checkpoints_and_writes`.

## Bugs hit and fixed (in order)

1. **Node version too old for Angular's CLI.** User's default Node was
   v22.16.0; Angular 22's CLI needs ≥22.22.3/24.15/26. Installed Node 24.18
   via the user's existing `nvm` rather than changing system Node. If
   `ng` commands start failing again, check `node --version` first.
2. **`GET /history` 500ing with a pydantic `ValidationError` on `content`.**
   Gemini (via `langchain-google-genai`) returns message content as a list
   of blocks (`[{"type": "text", "text": "..."}]`), not a plain string -
   code assumed `.content` was always `str`. Fixed with `extract_text()` in
   `agent/messages.py`, used everywhere `.content` is read.
3. **Raw tool output ("400.0") showing as an unstyled bubble in the UI.**
   Two causes, both fixed: (a) `/history` was including `role="tool"`
   messages at all - now filtered out entirely; (b) the live SSE stream was
   also relaying `ToolMessage` chunks through "token" events - now skipped
   via `isinstance(message_chunk, ToolMessage)`.
4. **Final answers sometimes being just the bare number, not a sentence.**
   Nothing told the model to phrase tool results conversationally. Fixed
   with a `SystemMessage` in `agent_node`.
5. **Every sidebar entry saying "New conversation," confusing to
   navigate.** Added `db.set_title_from_first_message()`, called from the
   `/chat` route - renames a session from the default title using the
   user's first message, exactly once (matched via `title ==
   DEFAULT_SESSION_TITLE` in the update filter).

## Security note

An API key was pasted directly into chat once during development. It was
flagged immediately and the user said they'd rotate it - **if you're
reading this later and unsure whether that happened, treat the key in
`backend/.env` as suspect and rotate it before relying on it.** Never put
real secrets in `.env.example`, commit messages, or this file.

## Known rough edges / possible next steps

- No streaming indicator distinguishes "waiting for approval" from "model
  is thinking" beyond the interrupt banner itself replacing the dots -
  that's intentional, not a bug, but worth revisiting if it's confusing.
- Session titles are just a truncated first message - fine for a demo, but
  a "summarize into a title" LLM call would read better for long first
  messages.
- No auth - anyone who can reach the API can read/delete any session. Fine
  for local dev, not fine if this ever gets deployed anywhere reachable.
- `checkpoint`/`metadata`/`value` fields in the two LangGraph-owned
  collections are opaque msgpack blobs by design - don't try to query into
  them from application code; go through the checkpointer's own API
  (`graph.aget_state()`, etc.) instead.
- Stated learning goals for this project, not yet started: a multi-agent
  setup (multiple LangGraph nodes/subgraphs or separate agents coordinating
  on one task, not just the single `agent`/`tools` loop today) and
  LangSmith tracing (`LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` env vars -
  `langsmith` is already a transitive dependency via LangGraph, nothing
  wired up yet). The `models/` + `repositories/` + `services/` layering
  introduced for `sessions` is meant to be the template once more
  agents/collections show up - each new domain concept should get its own
  trio of files rather than growing an existing one.
