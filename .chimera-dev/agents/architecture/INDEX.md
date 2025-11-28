# Architecture Index

## Current State (2024-11)

### Multi-Platform Strategy: Intentionally Deferred

Chimera runs in multiple modes (standalone API, CLI, Tauri desktop, future web). We discussed adding explicit capability negotiation but decided **not to build scaffolding yet**.

**Why wait:**
- Current abstractions (`client_context`, `AdapterProvider`, stateless API) provide extension points
- No concrete use case yet requiring platform-aware behavior
- Building infrastructure before the need = guessing

**When to revisit:**
- First full-stack blueprint that requires platform-specific features (terminal, file system, etc.)
- At that point, extend blueprint schema with `requires: ["terminal"]` or similar
- Clients check requirements before offering blueprints

### Key Architectural Boundaries

| Layer | Boundary | Notes |
|-------|----------|-------|
| `thread.py` | Dumb orchestration loop | No platform awareness, no business logic |
| `client_context` | Per-request values from client | cwd, model override. Flows: UserInput → ThreadDeps → Agent/Widget |
| Blueprints | Unit of "complete experience" | Will eventually include frontend rendering instructions |
| AdapterProvider | Frontend platform abstraction | TauriStorageAdapter, TauriConfigProvider, etc. |

### Files to Read

- `packages/core/src/chimera_core/types/user_input.py` — client_context definition
- `packages/core/src/chimera_core/thread.py` — ThreadDeps carries client_context
- `frontend/packages/platform/` — adapter interfaces
- `frontend/packages/desktop/src/adapters/` — Tauri implementations

### Open Questions (Not Blocking)

1. Should blueprints declare platform requirements? (defer until first use case)
2. Server `/capabilities` endpoint? (defer until remote deployment)
3. `platform` field in client_context? (defer until needed)
