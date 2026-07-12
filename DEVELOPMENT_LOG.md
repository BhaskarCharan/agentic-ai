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
    agent/graph.py      - the LangGraph graph (supervisor <-> tools, interrupt, checkpointer)
    agent/tools.py       - the multiply tool
    agent/llm.py          - swappable LLM factory
    agent/messages.py    - extract_text() - handles provider content-format quirks
    agent/weather_tools.py, weather_agent.py - the weather specialist (Phase 0)
    agent/gmail_tools.py, gmail_agent.py       - the Gmail specialist, read-only tool allowlist (Phase 2)
    agent/linkedin_tools.py, linkedin_agent.py  - the LinkedIn specialist, same shape (Phase 3)
    agent/supervisor_tools.py - wraps specialist agents as tools the supervisor can call;
                                 also where Gmail/LinkedIn's disconnected-account error handling lives
    composio_client.py      - shared Composio client construction (default + LangChain providers)
    api/chat.py           - controller: SSE endpoints (/chat, /resume), formats SSE only
    api/sessions.py       - controller: session CRUD, history
    api/integrations.py    - controller: Gmail/LinkedIn account-link status + connect/disconnect (Phase 1)
    api/dependencies.py    - FastAPI Depends() wiring: database -> repository -> service
    services/session_service.py       - business rules (default title, rename-once, ...)
    services/agent_service.py          - all graph interaction (astream, interrupt/resume, aget_state, adelete_thread) - controllers never touch `graph` directly
    services/integration_service.py     - connection management (link/status/disconnect) - client construction moved to composio_client.py
    repositories/session_repository.py - raw Mongo CRUD for the `sessions` collection
    models/session.py                   - SessionDocument (ours)
    models/checkpoint.py                 - CheckpointDocument/CheckpointWriteDocument (reference only)
    db.py                  - Motor client + get_database() only, no collection code
    config.py              - pydantic-settings, reads .env
frontend/
  src/app/
    chat.service.ts       - owns chat state as signals, hand-parses the SSE stream
    api.service.ts         - plain CRUD for sessions
    integrations.service.ts - plain CRUD for Gmail/LinkedIn account linking (Phase 1)
    integrations-panel.ts/.html/.css - sidebar panel: connect/status per toolkit
    sse.ts                  - manual SSE parser (fetch-based, not EventSource)
    app.ts/.html/.css      - sidebar + chat panel, single-component UI
DEVELOPMENT_LOG.md   - this file
MULTI_AGENT_ROADMAP.md - phase-by-phase plan for weather/Gmail/LinkedIn multi-agent work
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
- **How does LangSmith tracing turn on, and why does `config.py` write to
  `os.environ` when its own docstring says it's the only reader?** LangSmith
  tracing isn't a function you call - `langsmith`/`langchain-core` check
  `os.environ` directly, deep inside every LLM/tool/graph invocation, for
  `LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`/
  `LANGSMITH_ENDPOINT` (confirmed by reading `langsmith/utils.py`'s
  `tracing_is_enabled()` and `get_env_var()` in the installed package - it
  checks `LANGSMITH_*` first, falls back to legacy `LANGCHAIN_*`). Since
  pydantic-settings parses `.env` into its own `Settings` object without
  ever touching the real process environment, those vars would never reach
  the tracer if left purely as `Settings` fields. `config.py`'s
  `_export_langsmith_env()` is the one deliberate exception: it still reads
  the values the normal way (`.env` -> `Settings`), then re-exports them to
  `os.environ` purely so a *third-party* library's own env-var lookup can
  see them - `.env` stays the single source of truth, nothing else in the
  app reads `os.environ` directly. Off by default
  (`LANGSMITH_TRACING=false`) so a fresh clone never sends data anywhere
  until someone opts in. See README.md's "Optional: LangSmith tracing"
  section for the signup/setup steps.
- **Why does `IntegrationService` auto-provision Composio auth configs
  instead of expecting them pre-created in the dashboard, and why
  `connected_accounts.link()` instead of the more obviously-named
  `.initiate()`?** Both corrections to the original plan in
  `MULTI_AGENT_ROADMAP.md`'s Phase 1, found by reading the installed
  `composio==0.17.1` SDK's actual source/docstrings rather than trusting a
  remembered API shape: (1) `composio.toolkits.authorize()` - the
  convenience method that looks like the right one-liner - internally
  calls `connected_accounts.initiate()`, which its own docstring says is
  being retired for Composio-managed OAuth; using it would mean building
  Phase 1 on a method already flagged for removal. (2) That same
  convenience method also silently auto-creates an auth config if none
  exists for a toolkit - so `IntegrationService._get_or_create_auth_config`
  replicates that exact logic (`auth_configs.list` then `.create` on a
  miss) but built on the non-deprecated `connected_accounts.link()`
  instead, verified end-to-end against a real Composio account (real auth
  config created, real working redirect URL returned) before this was
  written up. (3) The whole Composio SDK used here is synchronous - every
  call in `IntegrationService` goes through `asyncio.to_thread(...)` so it
  doesn't block the FastAPI event loop, same reasoning as `MongoDBSaver`
  needing a sync `pymongo.MongoClient` in `agent/graph.py`.
- **Why doesn't the integrations panel show "connected as
  you@gmail.com" from just the connection status check, and where is that
  identity stored?** It isn't stored anywhere - there is no Mongo model for
  integrations at all (unlike `sessions`, which is genuinely ours;
  Composio's connection state lives entirely on Composio's own servers,
  never touching this app's MongoDB). A connection's status/token metadata
  (checked via `connected_accounts.list(...)`) only ever contains OAuth
  token fields (access token, scope, expiry) - never the account's email or
  name. Getting a display label requires an *additional* live call to the
  connected service's own "who am I" action through Composio
  (`GMAIL_GET_PROFILE` -> `data["emailAddress"]`, `LINKEDIN_GET_MY_INFO` ->
  `data["localizedFirstName"/"localizedLastName"]` - both confirmed live
  against real connected accounts), added as `IntegrationService._fetch_label`.
  Deliberately fetched fresh on every `GET /api/integrations` rather than
  cached in a new collection - chosen over adding an
  `integration_connections` Mongo model to avoid the cache going stale if a
  user disconnects on Composio's side directly; revisit only if the extra
  live calls prove too slow in practice. Tool execution required pinning a
  real toolkit version (`toolkits.get(toolkit).meta.version`) rather than
  the tempting `dangerously_skip_version_check=True` shortcut, which
  Composio's own error message warns against for real code.
- **Why does `IntegrationService.disconnect()` pass
  `revoke_on_delete=True`, and why wasn't it live-tested against a real
  connected account the way `connect`/status-check were?** Composio's
  `connected_accounts.delete()` defaults to *not* revoking the token with
  the provider if you omit that flag - it would just stop Composio from
  listing the connection while the underlying Google/LinkedIn token stays
  valid, which isn't what a user clicking "Disconnect" expects. Passing
  `revoke_on_delete=True` makes it a real revocation. This one genuinely
  wasn't live-tested end-to-end here (unlike everything else in Phase 1) -
  doing so would have disconnected the real Gmail/LinkedIn accounts just
  connected to verify the rest of this phase, forcing a real OAuth
  re-consent to fix. The underlying `connected_accounts.delete()` call was
  already proven live during this phase's own test-connection cleanup, so
  the mechanism is verified - just not through the app's actual API path.
  Confirm this one directly in the running app.

## MongoDB collections

Documented in detail with real field-level comments in `app/models/`;
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
6. **`GeneratorExit` traceback appearing as an errored run in LangSmith on
   the turn where a tool call needs approval** (the very first `/chat` in
   this app's demo flow), while the following `/resume` traced fine. Root
   cause: `AgentService._stream()` (see `services/agent_service.py`)
   deliberately stops consuming `graph.astream(...)` early on an interrupt
   (`yield ("interrupt", ...); return`) - the graph is paused, there's
   nothing more to read until `/resume`. Before the fix, that early `return`
   left the `astream()` async generator un-closed in the normal control
   flow; Python still closes it eventually via garbage collection, but only
   once this coroutine's frame is torn down later, throwing `GeneratorExit`
   into `astream()`'s last `yield o` from an asyncio finalizer callback
   *outside* the original call's context - which is what showed up
   unattached, looking like a failed run. Fixed by holding the astream
   generator in a variable and explicitly `await`ing `.aclose()` in a
   `finally` block around the loop, so the close happens synchronously,
   inline, attributed to the same call - same fix covers a client
   disconnecting mid-stream, not just the interrupt path. Verified with a
   standalone script driving a fake graph through `AgentService.start_turn`
   and confirming events after the interrupt are never produced and no
   warnings/exceptions leak once the caller stops iterating early.
   Functionally nothing was broken either before or after (turn 2 always
   worked) - this only changes *when and where* the generator's cleanup
   happens, since where it happens is what a tracer attributes it to.

   **Follow-up, after implementing the weather agent (Phase 0 of
   `MULTI_AGENT_ROADMAP.md`):** confirmed by reading LangGraph's actual
   `Pregel.astream()` source (`pregel/main.py`) that the `yield o` this
   traceback points at sits inside an `async with AsyncPregelLoop(...)`
   block wrapping the whole node execution - so **every** early close of
   the stream throws `GeneratorExit` through that scope, whether it's our
   explicit, immediate `aclose()` (the fix above) or a delayed GC one. This
   means the fix above does NOT make the LangSmith trace stop showing
   `GeneratorExit` - it only prevents the close from being orphaned onto an
   unrelated later context. **Every turn where the graph pauses on an
   `interrupt()` will show this in LangSmith, by design, and that's not
   fixable from our side** (LangSmith's tracing appears to flag any
   propagated `GeneratorExit` as a run error regardless of how cleanly it
   was closed). Confirmed live: a compound question with N tool calls in
   one `AIMessage` needs N sequential interrupt-approve round trips before
   finishing (the code deliberately loops `interrupt()` once per call in
   `tools_node`) - each of those N pauses shows a `GeneratorExit` in
   LangSmith, and only the final `/resume` that reaches `END` naturally
   traces clean. **This is expected, not a bug** - don't re-investigate it
   as one. The actual improvable thing here is UX, not tracing: one
   compound message currently needs multiple manual approve-clicks. Decided
   to leave that as-is rather than batch multiple pending tool calls into
   one `interrupt()` now - Phase 4's selective interrupts (only sensitive/
   write actions pause; reads like weather run silently) will shrink this
   naturally once most calls in a turn don't interrupt at all. Revisit the
   batching idea only if Phase 4 turns out not to be enough.
7. **`tools_node` would have raised `NotImplementedError: StructuredTool
   does not support sync invocation` the moment the supervisor actually
   called `weather_agent_tool`.** Caught while building Phase 0 of
   `MULTI_AGENT_ROADMAP.md`, before it ever hit a real request. Cause:
   `tools_node` executed every tool with the synchronous `tool.invoke(...)`;
   that's fine for `multiply` (a plain `def`), but `weather_agent_tool` (see
   `agent/supervisor_tools.py`) is `async def` - LangChain only allows
   calling an async-only tool via `.ainvoke()`, confirmed live with a
   throwaway `@tool async def` before touching the real code. Fixed by
   making `tools_node` itself `async def` and switching to `await
   tool.ainvoke(call["args"])` unconditionally - `.ainvoke()` also works
   for sync tools (runs them in a thread executor), so there's no need to
   branch on the tool's type. Any future specialist-agent wrapper tool
   (Gmail, LinkedIn, ...) will be `async def` for the same reason
   `weather_agent_tool` is (delegating to `some_agent.ainvoke(...)`), so
   this fix isn't weather-specific - it's load-bearing for the whole
   supervisor pattern from here on.
8. **A disconnected/expired Gmail or LinkedIn connection crashed the
   entire supervisor turn**, not just the one delegated question. Found
   live while building Phase 2/3 (`MULTI_AGENT_ROADMAP.md`): the two test
   connections used throughout Phase 1/2 building expired mid-session
   (Composio access tokens last about an hour - `expires_in: 3599` seen
   live - and `connected_accounts.refresh()` turned out to require a fresh
   consent redirect, not a silent token refresh, so there's no silent
   recovery today). Asking "read my latest email" with an expired
   connection raised `composio_client.BadRequestError` from deep inside
   `create_agent()`'s internal tool execution - and critically, this was
   **not** caught by any of LangGraph's/LangChain's own error handling; it
   propagated all the way up through `tools_node`'s `interrupt()`-based
   flow and killed the whole graph invocation, confirmed by driving the
   graph directly (bypassing the API) through a real interrupt-approve-
   resume cycle and watching it crash before the fix, then succeed with a
   graceful message after. Fixed with a broad `try/except Exception`
   around each specialist's `ainvoke()` call in
   `agent/supervisor_tools.py`'s `gmail_agent_tool`/`linkedin_agent_tool`,
   returning an actionable message ("check the Connected accounts panel
   and reconnect") instead of letting the exception escape - a deliberate,
   documented exception to "don't catch broadly," since there's no way to
   enumerate every failure mode a third-party API can produce and the
   alternative is the entire conversation dying. Verified live, end to
   end, for both Gmail and LinkedIn after the fix.

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
- Stated learning goal for this project, not yet started: a multi-agent
  setup (multiple LangGraph nodes/subgraphs or separate agents coordinating
  on one task, not just the single `agent`/`tools` loop today). The
  `models/` + `repositories/` + `services/` layering introduced for
  `sessions` is meant to be the template once more agents/collections show
  up - each new domain concept should get its own trio of files rather than
  growing an existing one.
