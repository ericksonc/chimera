# Test Infrastructure

## Run Commands
```bash
uv run pytest tests/python/ -v          # Python tests
cd frontend && pnpm test:run            # Frontend tests
uv run mypy packages/core/src/chimera_core/  # Type checking (full)
pre-commit run mypy --all-files         # Type checking (priority files only)
```

## Python (`tests/python/`)

**Unit vs Integration**: `core/unit/` for isolated logic, `core/integration/` for cross-module behavior.

**Key helpers** in `helpers/`:
- `FunctionModel` - deterministic LLM responses without mocking
- `ThreadHistoryBuilder` - fluent API for event sequences
- `conftest.py` fixtures: `mock_thread_deps`, `test_model`, `blueprint_builder`

## Frontend (`frontend/tests/`)

**Stack**: vitest + @testing-library/react + jsdom

**SSE mock** (`helpers/sse-mock.ts`):
- `createMockResponse(events)` - mock fetch response with SSE stream
- `VSP.*` builders - properly formatted VSP events
- `Scenarios.*` - common event sequences (simpleTextResponse, toolCallRequiringApproval)

**Gotcha**: jsdom's ReadableStream needs all data enqueued in `start()`, not `pull()`. See `createMockSSEStream`.

## Type Checking (2024-11-28)

**What's configured:**
- mypy + pyright in `pyproject.toml`
- Pylance settings in `.vscode/settings.json`
- Pre-commit hook runs mypy on priority files only

**What's checked (0 errors):**
- `thread.py`, `agent.py` (root of chimera_core)
- `threadprotocol/` directory (all files)

**What's NOT checked yet:**
- `widgets/`, `models/`, `spaces/graph_space.py` - explicitly ignored (module-level)
- `spaces/base.py`, `spaces/multi_agent_space.py` - have override signature issues
- `base_plugin.py` - TypeVar complexity with plugin system
- `ui/event_stream.py` - callable typing issues
- `primitives/` - implicit Optional issues

**Known patterns requiring `# type: ignore`:**
- pydantic-graph `StepContext` TypeVar limitations (`ctx.state.*`, `ctx.deps.*`, `ctx.inputs.*`)
- PAI `agent.iter()` overload complexity

## Principles

1. **Test behavior, not implementation** - if refactoring breaks tests, tests were wrong
2. **Minimal mocking** - FunctionModel over mocked LLM, real StorageAdapter over mocked fs
3. **Helpers earn their keep** - only add abstraction when 3+ tests benefit