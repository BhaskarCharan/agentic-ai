# Agentic AI Backend

FastAPI + LangGraph agent backend: a single `multiply` tool, MongoDB-backed
checkpointing (conversation history + resumability), human-in-the-loop
interrupts before every tool call, and SSE streaming to the frontend.

See `make help`-style targets in the `Makefile`: `install`, `dev`, `test`,
`lint`, `format`.
