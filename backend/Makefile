# Makefile for the backend service.
# Every target just delegates to `uv`, which manages the virtualenv and
# dependency resolution for us based on pyproject.toml / uv.lock.

.PHONY: install dev run test lint format clean

# Install all dependencies (including the "dev" group) into a local .venv.
install:
	uv sync --group dev

# Run the API with auto-reload, for local development.
dev:
	uv run uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 8000

# Run the API without reload, closer to how it would run in production.
run:
	uv run uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 8000

# Run the test suite.
test:
	uv run pytest

# Check code style/correctness without modifying files.
lint:
	uv run ruff check src tests

# Auto-fix lint issues and reformat code.
format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

# Remove caches and the virtualenv, for a totally clean rebuild.
clean:
	rm -rf .venv .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
