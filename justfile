# Chimera Monorepo - Task Runner

# Development
dev:
    just py-dev &
    just fe-dev

py-dev:
    uv run uvicorn chimera_api.main:app --reload --port 33003

fe-dev:
    cd frontend && pnpm dev

# Testing
test:
    just test-py
    just test-fe

test-py:
    uv run pytest

test-fe:
    cd frontend && pnpm test

# Linting
lint:
    uv run ruff check .
    cd frontend && pnpm lint

format:
    uv run ruff format .
    cd frontend && pnpm format

# Dependencies
sync:
    uv sync
    cd frontend && pnpm install

# Tauri
tauri-dev:
    cd frontend/packages/desktop && pnpm tauri dev

tauri-build:
    cd frontend/packages/desktop && pnpm tauri build

# CLI
cli:
    uv run chimera
