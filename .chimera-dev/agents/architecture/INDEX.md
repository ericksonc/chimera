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

### LLM Usage Analytics: Intentionally Deferred

Instrumentation exists but persistence/aggregation does not. This is deliberate.

**What exists:**
- `ChimeraAppUsageEvent` fires after every model API call (`vsp_event_stream.py:216-284`)
- Tracks: input/output/cache tokens, message_id, thread_id
- Events stream to client via SSE — infrastructure is solid

**What's missing:**
- No persistence (events fire and disappear)
- No cost calculation (tokens counted, not priced)
- No aggregation or historical queries

**Why wait — the unanswered questions:**

| Question | Options | Depends On |
|----------|---------|------------|
| **How?** | Client-side aggregation, server-side DB, external service | Where state lives |
| **Where?** | ThreadProtocol JSONL, SQLite, cloud | Query needs, data lifecycle |
| **For whom?** | End user, blueprint author, platform operator | Privacy boundaries, API surface |

These questions collapse to: **what's the deployment model?**

- Local-only → SQLite, user owns data
- Self-hosted team → Server DB, operator visibility
- SaaS multi-tenant → Billing integration, isolation requirements

**When to revisit:**
- First concrete use case requiring usage history (budgets, billing, optimization)
- Deployment model decision that clarifies data ownership
- At that point, add persistence at `handle_model_response()` or client store

**Extension point:** The `chimera-app-usage` event is the right abstraction. Future persistence layers hook there.

### Frontend Integration Strategy: Base + Blueprint Unification

Two codebases will merge: Chimera's backend wiring + test-chm's UI patterns.

**Chimera frontend (`/chimera/frontend`) — keep:**
- `ChimeraTransport` - SSE bridge, delta accumulation, persistence (`chimera-transport.ts`)
- `hydrateFromEvents()` - JSONL → UIMessage reconstruction (`jsonl-hydrator.ts`)
- `ThreadProtocol` event schema v0.0.7 (`thread-protocol.ts`)
- `StorageAdapter` interface - platform abstraction (`adapters.ts`)
- Test infrastructure - `sse-mock.ts`, event builders

**test-chm (`/test-chm`) — the "Base" concept:**
- Base = self-contained UI layout filling viewport
- Registered with id/name/description, rendered by `BaseRenderer`
- State isolated per-Base via `BaseProvider` Map
- Currently mock-only, needs real transport wiring

**Target Bases for first integration:**
| Base | Pattern | Blueprint Use Case |
|------|---------|-------------------|
| `chatbot-artifact` | 70/30 split | Code assistant, doc generation |
| `floating-chat` | Corner widget | Embedded assistant |
| `mission-control` | Agent dashboard | Autonomous agent viz |

**Wiring plan:**
1. Base replaces mock `streamWords()` with real `ChimeraTransport` SSE
2. Blueprint provides agent.py + blueprint.json backend
3. Base.tsx moves into `defs/blueprints/{name}/`
4. Thread list scoped to active Base/Blueprint (not flat list)
5. Default "chat-only" blueprint for Bases without 1:1 mapping

**When to execute:**
- First full-stack blueprint that needs polished UI
- UI playground (`test-chm`) stabilizes on component patterns
- At that point: wire one Base end-to-end as reference implementation

### Open Questions (Not Blocking)

1. Should blueprints declare platform requirements? (defer until first use case)
2. Server `/capabilities` endpoint? (defer until remote deployment)
3. `platform` field in client_context? (defer until needed)
