# Chimera

## Agent Loading

When the user says **"be {agent}"** where agent is one of:
- `architecture` - System design, boundaries, protocols
- `widgets` - Widget development and patterns
- `frontend` - React/TypeScript UI components
- `tauri` - Desktop app and Rust backend

**You MUST read both files before proceeding:**
```
.chimera-dev/agents/{agent}/CLAUDE.md
.chimera-dev/agents/{agent}/INDEX.md
```

If no further instructions follow "be {agent}", confirm you've loaded the context and await direction.

## Project Layout

```
packages/           Python (uv workspace)
  core/             chimera_core - agents, threads, spaces, widgets
  api/              chimera_api - FastAPI backend
  cli/              chimera_cli - Textual TUI

frontend/           TypeScript (pnpm workspace)
  packages/core/    React components, hooks, stores
  packages/desktop/ Tauri app
  packages/platform/ Adapter interfaces

defs/               Definitions
  blueprints/       {name}/blueprint.json + agent.py + Base.tsx
  agents/           YAML agent configs

.chimera-dev/       Agent instructions, design docs (versioned)
.chimera-local/     Personal blueprints/agents (gitignored)
```

## Commands

```bash
just sync       # Install all dependencies
just dev        # Start API + Tauri dev
just test       # Run all tests
just tauri-dev  # Desktop app only
```

## Imports

```python
from chimera_core.agent import Agent
from chimera_core.spaces import GenericSpace
from chimera_api.main import app
from chimera_cli.app import run
```
