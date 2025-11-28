# Test Infrastructure

## Run Commands
```bash
uv run pytest tests/python/ -v          # Python tests
cd frontend && pnpm test:run            # Frontend tests
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

## Principles

1. **Test behavior, not implementation** - if refactoring breaks tests, tests were wrong
2. **Minimal mocking** - FunctionModel over mocked LLM, real StorageAdapter over mocked fs
3. **Helpers earn their keep** - only add abstraction when 3+ tests benefit