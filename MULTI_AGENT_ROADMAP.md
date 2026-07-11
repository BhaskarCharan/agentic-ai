# Multi-Agent Roadmap: Weather + Gmail + LinkedIn via Composio

**Read this first if you're picking this project up in a fresh chat.** This
file is the standalone plan for the next feature: turning the current
single-tool (`multiply`) chat agent into a **supervisor** that can also read
Gmail, look up LinkedIn, and check the weather - all from one chat message,
e.g. *"Read my latest mail and summarize it, and what's the weather in
Hyderabad today?"*.

It assumes you have NOT read the rest of the conversation that produced this
file. Start here, then read `DEVELOPMENT_LOG.md` for how the *current* app
(session management, checkpointing, interrupts, SSE streaming) is built and
why - this file only covers what's **new**.

---

## 1. What exists today (as of writing this file)

A FastAPI + LangGraph chat backend with:

- One agent node, one tool (`multiply`), a `tools_condition` conditional
  edge, MongoDB checkpointing (`MongoDBSaver`), and a per-tool-call
  `interrupt()` for human approval before any tool actually runs.
- A layered backend: `models/` (Pydantic shapes) -> `repositories/` (raw
  Mongo CRUD) -> `services/` (business logic: `SessionService` for the
  `sessions` collection, `AgentService` for all LangGraph interaction) ->
  `api/` (FastAPI routers = controllers, thin, no business logic) wired
  together via `api/dependencies.py`'s `Depends()` chain.
- LangSmith tracing, off by default, toggled via `LANGSMITH_TRACING=true` in
  `.env` (see `app/config.py`'s `_export_langsmith_env()`).
- An Angular frontend that renders one chat panel, hand-parsing an SSE
  stream (`sse.ts`) - no other UI surfaces yet.

Full file map and the "why" behind every existing decision: see
`DEVELOPMENT_LOG.md`. **Do not duplicate that file's content here** - if
something about the *current* architecture is unclear, read it there, not in
this roadmap.

### Locked-in decisions for this feature (already discussed, don't re-litigate)

1. **Architecture pattern: supervisor with specialist-agents-as-tools.** One
   supervisor node (an evolution of today's `agent_node`) gets 3 new tools
   bound alongside `multiply`: `weather_agent`, `gmail_agent`,
   `linkedin_agent`. Each of those tools is a thin wrapper that invokes its
   *own* small compiled sub-graph (its own mini agent loop with its own
   toolset) and returns that sub-agent's final answer as a string. This is
   **not** the `Command(goto=...)`/handoff "network" pattern - specialists
   never talk to each other, only to the supervisor, and the supervisor
   treats each of them as a callable tool, same mechanism as `multiply`
   today.
   - Why this pattern and not `langgraph-supervisor` (the prebuilt package
     that does this exact thing): hand-roll it first, same reasoning as why
     `graph.py` hand-rolls the agent/tools loop instead of using
     `create_react_agent` - the point is learning the coordination
     mechanics. `langgraph-supervisor` is a good thing to swap in *after*
     you've built one by hand and understand what it hides.
   - Why compound questions ("read mail AND weather") will just work with
     no extra plumbing: `tools_node` in `agent/graph.py` already loops over
     `last_message.tool_calls` (plural) - Gemini can return multiple tool
     calls in one `AIMessage`, and the existing code already executes all
     of them in one graph step. Even if the model calls them one at a time
     across two loop iterations instead, the `agent <-> tools` loop just
     runs twice before producing a final answer either way. **No new
     control-flow code is needed for the compound-question requirement** -
     it falls out of the architecture that already exists once the tools
     themselves exist.

2. **Composio user identity: single hardcoded `user_id`.** This app has no
   auth today (flagged as a known gap in `DEVELOPMENT_LOG.md`). Rather than
   build real auth before this feature, use one fixed identifier everywhere
   Composio needs a `user_id`:
   ```python
   # config.py addition
   composio_user_id: str = "me"
   ```
   This is a deliberate scope decision for a personal/single-user learning
   project - revisit if this app ever needs to support more than one real
   person.

3. **Weather does NOT go through Composio.** Weather is public data, no
   OAuth/consent needed. Use **Open-Meteo** (free, no API key,
   verified working live while writing this doc - see Phase 0 below) via a
   plain custom `@tool`, not an external SDK.

4. **Selective interrupts, added in Phase 4, not before.** Today every tool
   call pauses for approval. Once Gmail/LinkedIn can *write* (send an email,
   post to LinkedIn), only writes should interrupt - reads (fetch latest
   email, fetch profile, get weather) should run silently. Don't build this
   until Phase 4; earlier phases keep the current "confirm everything"
   behavior so as not to change two things at once.

---

## 2. Package versions - current vs. what to add

Confirmed live against this repo's actual installed environment and PyPI on
the day this file was written. **Re-check versions before installing** -
this is a fast-moving ecosystem (Composio in particular has gone through a
v2 -> v3 SDK rewrite; some of its own sub-package READMEs on PyPI still show
v2-style code samples even under the current version number, so verify
against **https://docs.composio.dev** at implementation time, not just this
table).

### Already installed (backend), confirmed via `uv pip list`

| Package | Installed version | Relevant floor in `pyproject.toml` |
|---|---|---|
| Python | 3.11.14 | `requires-python = ">=3.11"` |
| `fastapi` | 0.139.0 | `>=0.115.0` |
| `langgraph` | 1.2.9 | `>=0.2.60` (pin is stale - actual installed is much newer) |
| `langgraph-checkpoint-mongodb` | 0.4.0 | `>=0.1.0` |
| `langgraph-prebuilt` | 1.1.0 | transitive |
| `langchain` | 1.3.13 | not pinned directly yet (transitive via `langchain-google-genai`) |
| `langchain-core` | 1.4.9 | transitive |
| `langchain-google-genai` | 4.2.7 | `>=2.0.0` |
| `langsmith` | 0.10.2 | `>=0.10.0` |
| `motor` | 3.7.1 | `>=3.6.0` |
| `pydantic` | 2.13.4 | transitive |
| `pydantic-settings` | 2.14.2 | `>=2.6.0` |

**Housekeeping worth doing at the start of Phase 0, unrelated to new
features:** the `langgraph>=0.2.60` floor in `pyproject.toml` is very stale
next to the actually-installed `1.2.9` - consider bumping the declared floor
so a fresh `uv sync` on another machine doesn't resolve something
unexpectedly old. Same goes for pinning `langchain` explicitly now that
Phase 2+ will depend on `composio-langchain`'s version constraint on it.

### Frontend (Angular), confirmed via `package.json` / `node --version`

| Package | Version |
|---|---|
| Node.js (local) | v22.16.0 (works today; only matters if Angular's floor changes) |
| `@angular/core` et al. | `^22.0.0` |
| `typescript` | `~6.0.2` |
| `rxjs` | `~7.8.0` |

No frontend package changes needed until Phase 1 (the consent/linked-accounts
UI) - that's plain Angular, no new libraries required.

### New dependencies needed, by phase - **verify exact versions again before installing**, these are current as of this writing

| Phase | Package | Confirmed version (PyPI, today) | Confirmed compatible with this repo because |
|---|---|---|---|
| 0 | `httpx` (move from dev-only to a main dependency) | 0.28.1 already installed | Already vendored transitively; just needs to move into `dependencies`, not `[dependency-groups].dev`, since the weather tool needs it at runtime, not just in tests |
| 1/2/3 | `composio` | 0.17.1 | `requires-python = ">=3.10,<4"`; needs `pydantic>=2.13.4` (we have exactly 2.13.4) |
| 1/2/3 | `composio-langchain` | 0.17.1 | Declares `langchain<2.0.0,>=1.3.9` - our installed `langchain==1.3.13` satisfies this directly, no upgrade needed |
| (alt.) | `composio-langgraph` | 0.17.1 | Declares `langgraph<2.0.0,>=1.0.2` (wide open, no conflict) - **but its PyPI README shows old (`ComposioToolSet`, `composio-cli`) v2-style API**; prefer `composio-langchain` unless you specifically need something LangGraph-native it offers - check current docs before choosing |
| (optional, for MCP-based tool-fetching instead of the SDK) | `langchain-mcp-adapters` | 0.3.0 | `langchain-core<2.0.0,>=1.0.0` - compatible; lets you pull tools from Composio's own hosted MCP endpoint per toolkit instead of the Python SDK - see the note in Phase 2 |
| (optional swap-in later, once you understand the hand-rolled version) | `langgraph-supervisor` | 0.0.31 | `langgraph<2.0.0,>=1.0.2`, `langchain-core<2.0.0,>=1.0.0` - both satisfied |
| (Section 8, if pursued) | `mcp` (official SDK) | 1.28.1 | `requires-python>=3.10` |
| (Section 8, if pursued) | `fastmcp` | 3.4.4 | `requires-python>=3.10` - higher-level, easier for a simple server than the raw `mcp` SDK |

---

## 3. Phase 0 - Weather agent (zero external accounts, build this first)

**Goal:** prove the supervisor + specialist-agent-as-tool pattern end to
end, with no OAuth/consent complexity in the way. This validates the
architecture before Phase 1's real (and more fiddly) account-linking work.

**Why Open-Meteo:** free, no API key/signup, two simple GET calls. Verified
live while writing this doc:

```bash
curl "https://geocoding-api.open-meteo.com/v1/search?name=Hyderabad&count=1"
# -> {"results":[{"name":"Hyderabad","latitude":17.38405,"longitude":78.45636, ...}]}

curl "https://api.open-meteo.com/v1/forecast?latitude=17.398945&longitude=78.457085&current=temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m"
# -> {"current":{"temperature_2m":29.6,"weather_code":3,"relative_humidity_2m":54,"wind_speed_10m":9.4}, ...}
```

### New/changed files

```
backend/src/app/agent/
  weather_tools.py        - NEW: geocode() + get_current_weather() as @tool functions
  weather_agent.py         - NEW: builds a small create_react_agent() bound to weather_tools
  supervisor_tools.py       - NEW: wraps weather_agent as a callable tool for the supervisor
  graph.py                   - CHANGED: TOOLS list (or an equivalent for the supervisor) gains the new wrapper tool
```

Follow the existing pattern in `agent/tools.py` exactly - a plain typed
function, `@tool`-decorated, with a docstring the model reads to decide when
to call it:

```python
# agent/weather_tools.py
"""Tools for the weather specialist agent - Open-Meteo, no API key needed."""

import httpx
from langchain_core.tools import tool


@tool
async def get_current_weather(city: str) -> str:
    """Get the current weather for a city name (e.g. "Hyderabad", "London").

    Geocodes the city name to coordinates first, then fetches current
    conditions. Returns a short plain-text summary.
    """
    async with httpx.AsyncClient() as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
        )
        results = geo.json().get("results")
        if not results:
            return f"Could not find a location matching '{city}'."
        lat, lon, resolved_name = results[0]["latitude"], results[0]["longitude"], results[0]["name"]

        forecast = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m",
            },
        )
        current = forecast.json()["current"]

    return (
        f"Current weather in {resolved_name}: {current['temperature_2m']}°C, "
        f"{current['relative_humidity_2m']}% humidity, "
        f"wind {current['wind_speed_10m']} km/h."
    )


WEATHER_TOOLS = [get_current_weather]
```

The specialist agent itself - this is the first place `create_react_agent`
gets used in this codebase, deliberately (see decision #1 above for why now
vs. earlier):

```python
# agent/weather_agent.py
"""The weather specialist - a small ReAct agent the supervisor calls as a tool."""

from langgraph.prebuilt import create_react_agent

from app.agent.llm import get_llm
from app.agent.weather_tools import WEATHER_TOOLS

# No checkpointer here - this sub-agent's internal reasoning doesn't need
# its own persisted history; only the top-level supervisor's conversation
# does (via the existing MongoDBSaver in build_graph()).
weather_agent = create_react_agent(get_llm(), WEATHER_TOOLS)
```

And the wrapper that makes it callable as one tool from the supervisor:

```python
# agent/supervisor_tools.py (new file - or fold into tools.py if you prefer
# one file; separate is clearer once Gmail/LinkedIn wrappers join it)
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.agent.messages import extract_text
from app.agent.weather_agent import weather_agent


@tool
async def weather_agent_tool(request: str) -> str:
    """Delegate a weather-related question to the weather specialist agent.
    Pass the user's weather question as-is, e.g. "what's the weather in
    Hyderabad today?"."""
    result = await weather_agent.ainvoke({"messages": [HumanMessage(content=request)]})
    return extract_text(result["messages"][-1].content)
```

Then in `graph.py`, add `weather_agent_tool` to the list bound via
`.bind_tools(TOOLS)` alongside `multiply` - no other change to
`agent_node`/`tools_node`/the graph wiring is needed, which is the whole
point of this pattern.

### Acceptance criteria for Phase 0

- Asking *"what's the weather in Hyderabad?"* in the existing chat UI
  produces a real, current answer (still goes through the existing
  `interrupt()` approval banner, since selective interrupts aren't built
  until Phase 4 - approving `weather_agent_tool` should feel identical to
  approving `multiply` today).
- Asking a **compound** question (*"what's 6 times 7 and what's the weather
  in Hyderabad?"*) produces one final answer covering both, with no new code
  beyond what's listed above - this is what proves decision #1's claim about
  compound questions "just working."
- Existing tests (`make test`) still pass unmodified.

---

## 4. Phase 1 - Composio account plumbing + consent UI

**Goal:** get to the point where the backend can show "Gmail: connected as
you@gmail.com" / "LinkedIn: not connected" and a user can click "Connect" and
complete a real OAuth consent flow. **No Gmail/LinkedIn agent logic yet** -
this phase is purely about the linking mechanism, so Phase 2/3 have a
working connection to build against instead of debugging OAuth and agent
logic at the same time.

### Setup (manual, one-time, outside the codebase)

1. Sign up at Composio, get an API key.
2. Create an **Auth Config** per toolkit you'll use (Gmail, LinkedIn) in the
   Composio dashboard - this is their term for "the OAuth app registration
   blueprint" for that service.
3. Add to `backend/.env` / `.env.example`:
   ```
   COMPOSIO_API_KEY=
   COMPOSIO_USER_ID=me
   ```
   and a matching field in `config.py`, same pattern as `google_api_key`.

### New/changed files

```
backend/src/app/
  services/integration_service.py   - NEW: wraps Composio's connection-management calls
  api/integrations.py                  - NEW: controller - GET status, POST connect
  api/dependencies.py                   - CHANGED: add get_integration_service
  api/schemas.py                          - CHANGED: add IntegrationStatusOut, etc.
  main.py                                  - CHANGED: include_router(integrations.router)
frontend/src/app/
  integrations.service.ts              - NEW: CRUD against /api/integrations
  integrations-panel/*                  - NEW: small component, one row per toolkit
```

### What `IntegrationService` needs to do (verify exact Composio method
names against **current** docs when you implement this - the SDK has
changed shape between major versions, don't trust a remembered snippet over
`docs.composio.dev`):

1. **List connection status** for each toolkit (Gmail, LinkedIn) for
   `settings.composio_user_id` - "connected" vs "not connected", and if
   connected, some display detail (e.g. the connected email address) if the
   API exposes it.
2. **Initiate a connection** for a given toolkit - this returns a redirect
   URL; your frontend sends the browser there, the user grants consent on
   Google's/LinkedIn's real OAuth screen, and Composio marks the connection
   active on their side once it's done.
3. (Optional) **Disconnect** a toolkit.

This service is intentionally the *only* place that imports the `composio`
SDK - same reasoning as `agent/llm.py` isolating the Gemini-specific client,
or `db.py` isolating Motor. If Composio's SDK changes shape again, this is
the one file that needs to change.

### Controller sketch

```python
# api/integrations.py
from fastapi import APIRouter

from app.api.dependencies import IntegrationServiceDep
from app.api.schemas import IntegrationStatusOut

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatusOut])
async def list_integrations(service: IntegrationServiceDep):
    return await service.list_statuses()


@router.post("/{toolkit}/connect")
async def connect_integration(toolkit: str, service: IntegrationServiceDep):
    return {"redirect_url": await service.initiate_connection(toolkit)}
```

### Frontend

A small panel (new route or a section in the existing sidebar) listing
Gmail/LinkedIn with a status badge and a "Connect" button that just does
`window.location.href = redirect_url` (or opens a new tab) - this is a
plain OAuth redirect, nothing LangGraph/streaming-specific about it, so it
doesn't need to touch `sse.ts`/`chat.service.ts` at all.

### Acceptance criteria for Phase 1

- Visiting the integrations panel with nothing connected shows both as "not
  connected."
- Clicking "Connect" on Gmail completes a real Google OAuth consent screen
  and returns to the app; the panel now shows "connected."
- No changes yet to the chat/agent graph - this phase is additive and
  doesn't touch `agent/graph.py`.

---

## 5. Phase 2 - Gmail agent

**Goal:** *"read my latest mail and summarize it"* works end to end.

### Two ways to get Gmail tools - pick one, verify current docs before committing

**Option A - Composio's Python SDK tool objects** (what `composio-langchain`
is for): fetch ready-to-bind `BaseTool` objects for the Gmail toolkit,
scoped to `settings.composio_user_id`, and bind them into a
`create_react_agent()` the same way `weather_agent.py` does. This keeps
everything in the same SDK you're already using for connection management
in Phase 1.

**Option B - Composio's hosted MCP endpoint per toolkit**, consumed via
`langchain-mcp-adapters`: Composio exposes each toolkit as its own MCP
server; instead of the `composio`/`composio-langchain` SDK calls, your agent
connects to that MCP endpoint and gets the same tools via the Model Context
Protocol instead. This is worth knowing about mainly because it's the same
mechanism you'd use for Section 8's MCP question, just in the *client*
direction (consuming an MCP server) rather than the *server* direction
(exposing one) - seeing both directions is useful for the learning goal, but
don't feel obligated to use it here if Option A is simpler to wire up.

Recommendation: **start with Option A** (consistent with Phase 1's SDK
usage), keep Option B in your back pocket once Section 8's MCP work is
underway and the concept is familiar from the consumer side too.

### New/changed files (mirrors Phase 0's shape exactly)

```
backend/src/app/agent/
  gmail_tools.py     - NEW: Composio-provided Gmail tools (read/search/summarize-relevant ones)
  gmail_agent.py      - NEW: create_react_agent() bound to gmail_tools
  supervisor_tools.py  - CHANGED: add gmail_agent_tool, same wrapper shape as weather_agent_tool
  graph.py               - CHANGED: bind gmail_agent_tool alongside the others
```

### Acceptance criteria for Phase 2

- With Gmail connected (Phase 1), asking *"read my latest email and
  summarize it"* returns an accurate summary of a real message in the
  connected inbox.
- The compound-question case from Phase 0's acceptance criteria still works
  with Gmail added to the mix (e.g. mail summary + weather in one message).

---

## 6. Phase 3 - LinkedIn agent

Same shape as Phase 2, second toolkit. By this point the pattern
(Composio-connected toolkit -> `create_react_agent()` -> wrapper tool -> add
to supervisor's tool list) should be close to copy-paste, which is the
payoff of doing Gmail first.

```
backend/src/app/agent/
  linkedin_tools.py
  linkedin_agent.py
  supervisor_tools.py   - CHANGED: add linkedin_agent_tool
  graph.py                 - CHANGED: bind linkedin_agent_tool
```

**Acceptance criteria:** a LinkedIn-only question works, and a
three-way compound question (mail + weather + LinkedIn, all in one message)
still produces one coherent final answer.

---

## 7. Phase 4 - Compound-question polish + selective interrupts

Now that all three specialists exist, revisit the two things deliberately
deferred earlier:

1. **Selective interrupts.** Add a small set in `agent/graph.py`:
   ```python
   # Only these tool names pause for human approval; everything else
   # (reads: weather, mail summarization, profile lookups) runs straight
   # through. Add a tool name here the moment it can *write* somewhere
   # (send an email, post to LinkedIn, etc.).
   SENSITIVE_TOOLS = {"gmail_send_email", "linkedin_create_post"}
   ```
   and change `tools_node`'s loop to only call `interrupt()` when
   `call["name"] in SENSITIVE_TOOLS`, running everything else immediately.
   This is the point where the `interrupt()` pattern you already built
   stops being "confirm literally everything" (fine for a demo with one
   harmless `multiply` tool) and starts being "confirm the things that
   actually matter" (necessary once tools can send real email or post
   publicly).
2. **Supervisor prompt tuning.** Update the `_SYSTEM_PROMPT` in
   `agent/graph.py` to explicitly mention all specialists and encourage
   answering multi-part questions completely - e.g. "If a user's message
   has multiple parts (e.g. asking about email and weather in the same
   message), address every part before giving your final answer."
3. **Per-agent LangSmith run naming** - pass `name="weather_agent"` (etc.)
   to each `create_react_agent()` call, so traces in LangSmith clearly show
   which specialist handled which part of a compound request. Purely a
   debugging/observability nicety, no behavior change.

---

## 8. Optional stretch add-ons (not phased, pick up anytime after Phase 4)

- **A connectors registry.** Right now each new integration means editing
  `graph.py`'s tool list by hand. A small config mapping toolkit name ->
  Composio auth config id -> which wrapper tool/module handles it turns
  "add a 6th integration" into a data change, following the same
  "each domain concept gets its own trio of files" convention established
  for `sessions`/`agent` in `DEVELOPMENT_LOG.md`.
- **LangGraph long-term `Store`** (distinct from the checkpointer used
  today) for cross-conversation preferences - e.g. "my default city is
  Hyderabad" remembered across sessions, not just within one thread's
  checkpoint history. A good second LangGraph persistence primitive to
  learn, since it solves a genuinely different problem than checkpointing.
  Also worth exploring `langgraph-supervisor` as a prebuilt swap-in for
  the hand-rolled supervisor pattern, once you've built it once by hand
  (decision #1) - compare what it gives you for free against what you wrote
  yourself.

---

## 9. "If I want this as an MCP server, is it easy to do?"

Depends which of two things you mean - genuinely different amounts of work:

### (a) Expose the individual tools (weather / Gmail actions / LinkedIn
actions / `multiply`) as an MCP server, so any MCP client (Claude Desktop,
another agent, Claude Code itself) can call them directly

**Easy.** Every tool in this plan is already a plain typed Python function
with a docstring (`agent/weather_tools.py`, etc.) - that's exactly the shape
`fastmcp` or the official `mcp` SDK want. Wrapping them is close to
mechanical:

```python
# mcp_server.py - sketch, not wired into anything yet
from fastmcp import FastMCP

from app.agent.weather_tools import get_current_weather
# ... import the others similarly

mcp = FastMCP("agentic-ai-tools")
mcp.tool()(get_current_weather)
# mcp.tool()(...) for each other tool

if __name__ == "__main__":
    mcp.run()
```

This would run as a **separate process/entrypoint** from the FastAPI app -
it doesn't touch `main.py`, the graph, or the layered services at all. It's
a new, independent "front door" onto the same underlying tool functions.

### (b) Expose the whole chat agent (sessions, threads, the interrupt/resume
human-in-the-loop flow, SSE streaming) as one MCP-callable thing

**Doable, but genuinely more work, not a thin wrapper.** The reason: MCP's
core tool-call model is simple request/response (call a tool, get a
result), while this app's most interesting behavior - pausing mid-turn to
ask a human "should I run this?" via `interrupt()`, and resuming later via a
separate `/resume` call - doesn't map onto a single MCP tool call cleanly.

The interesting wrinkle: MCP's newer **elicitation** capability (a server
asking the connected client to prompt its user for input *mid*-tool-call,
then continuing with the answer) is conceptually the same shape as
`interrupt()`/`Command(resume=...)`. Bridging LangGraph's interrupt payload
into an MCP elicitation request - and the resume value back into
`Command(resume=...)` - is a real but bounded translation layer, not
"add a decorator." Budget this as its own small project if you pursue it,
not a Phase 0-sized task.

**Why this is easy to *add* regardless of which one you pick:** the layering
work already done (`AgentService`, `SessionService`, both FastAPI-agnostic)
means an MCP server - either flavor - is a new controller-equivalent that
calls the *same* services `api/chat.py`/`api/sessions.py` already call. You
would not be rewriting agent logic to add an MCP front end; that's the
concrete payoff of the Repository + Service Layer refactor from earlier in
this project, for exactly this kind of "add a second interface" situation.

---

## 10. Suggested order to actually execute this

1. Phase 0 (weather) - lowest risk, validates the architecture.
2. Phase 1 (Composio linking + consent UI) - unblocks Phases 2 and 3;
   nothing about Gmail/LinkedIn agents can be tested without it.
3. Phase 2 (Gmail), then Phase 3 (LinkedIn) - same pattern twice, second one
   should be fast.
4. Phase 4 (polish: selective interrupts, prompt tuning, trace naming).
5. Section 8 add-ons and the MCP question, opportunistically, once the core
   multi-agent flow is solid.
