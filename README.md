# Agentic AI Chat

A small AI chat app with one tool (`multiply`), built to demonstrate an
agent backend with persistent history, checkpoints, and human-in-the-loop
interrupts, streamed to a simple Angular frontend over SSE.

- **Backend**: FastAPI + LangGraph (agent graph, MongoDB checkpointing,
  interrupt/resume) + Gemini as the LLM. See [backend/README.md](backend/README.md)
  for backend-specific details.
- **Frontend**: Angular (latest), standalone components + signals, plain
  CSS. Consumes the backend's SSE stream via `fetch` (not `EventSource`,
  since it needs to POST a JSON body).
- **Database**: MongoDB — stores both LangGraph's conversation checkpoints
  and a small `sessions` collection used for the sidebar list.

## Prerequisites

| Tool    | Version                          | Notes                                              |
|---------|-----------------------------------|-----------------------------------------------------|
| Python  | 3.11+                             | managed by `uv`                                    |
| uv      | latest                             | https://docs.astral.sh/uv/getting-started/installation/ |
| Node.js | 22.22.3+ / 24.15+ / 26+            | required by Angular's latest CLI. Use `nvm use 24` if your default Node is older. |
| MongoDB | any recent version, running locally on `mongodb://localhost:27017` | `brew services start mongodb-community` or run `mongod` directly |
| Gemini API key | — | get one at https://aistudio.google.com/app/apikey |

## 1. Backend setup

```bash
cd backend
cp .env.example .env
# edit .env and set GOOGLE_API_KEY to your own key
# (never commit .env or share the key anywhere - it's gitignored)

make install   # uv sync --group dev
make dev       # runs on http://localhost:8000, auto-reloads on file changes
```

Verify it's up:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

Other useful backend commands (see [backend/Makefile](backend/Makefile)):

```bash
make test     # run pytest
make lint     # ruff check
make format   # ruff check --fix + ruff format
```

## 2. Frontend setup

In a second terminal:

```bash
cd frontend
nvm use 24        # only needed if your default Node is older than Angular requires
npm install       # already done if you just cloned this repo fresh; safe to re-run
npx ng serve      # runs on http://localhost:4200
```

Open **http://localhost:4200** in your browser.

## 3. Using the app

1. Click **+ New chat**, or the app auto-creates one on first load.
2. Ask something like *"what's 6 times 7?"*.
3. The response streams in token-by-token. Before the `multiply` tool
   actually runs, the agent pauses and a banner appears asking you to
   **Approve** or **Decline** the tool call - that's the LangGraph
   `interrupt()` in [backend/src/app/agent/graph.py](backend/src/app/agent/graph.py).
4. Approve it, and the final answer streams in.
5. Refresh the page or restart the backend - past conversations are still
   there, loaded straight from MongoDB checkpoints (no separate "messages"
   table needed).

## Troubleshooting

- **`ng serve` complains about Node version**: run `nvm use 24` (or install
  a Node version satisfying `^22.22.3 || ^24.15.0 || >=26.0.0`) before
  running any Angular CLI command.
- **Backend fails to start / Mongo connection errors**: make sure MongoDB
  is running locally (`pgrep mongod`) and `MONGO_URI` in `backend/.env`
  points at it.
- **Chat requests fail with a Gemini/auth error**: check `GOOGLE_API_KEY`
  in `backend/.env` is set to a valid, non-expired key.
- **CORS errors in the browser console**: confirm `CORS_ORIGINS` in
  `backend/.env` includes `http://localhost:4200` (it does by default).
