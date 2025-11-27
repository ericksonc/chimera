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

# Linting & Formatting
lint:
    uv run ruff check packages/
    cd frontend && pnpm lint

format:
    uv run ruff format packages/
    cd frontend && pnpm format

format-check:
    uv run ruff format --check packages/
    cd frontend && pnpm format:check

# CI (runs all checks)
ci:
    uv run ruff check packages/
    uv run ruff format --check packages/
    cd frontend && pnpm lint
    cd frontend && pnpm format:check
    cd frontend && pnpm check
    uv run pytest

# Pre-commit hooks
setup-hooks:
    uv run pre-commit install

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
