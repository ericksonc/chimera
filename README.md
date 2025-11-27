# Chimera

Multi-agent orchestration system with Python backend and TypeScript/Tauri frontend.

## Structure

- `packages/` - Python packages (uv workspace)
  - `core/` - Core framework (agents, threads, widgets, spaces)
  - `api/` - FastAPI backend
  - `cli/` - Textual-based CLI
- `frontend/` - TypeScript/Tauri (pnpm workspace)
  - `packages/core/` - Platform-agnostic UI components
  - `packages/desktop/` - Tauri desktop app
  - `packages/platform/` - Adapter interfaces
  - `packages/web/` - Web version
- `defs/` - Chimera definitions
  - `blueprints/` - Blueprint configurations (JSON + Python + TSX)
  - `agents/` - Agent YAML definitions
- `.chimera-dev/` - Agent instructions and design docs
- `.chimera-local/` - Personal data (gitignored)
- `tests/` - Test suites

## Commands

```bash
# Install dependencies
just sync

# Development (Python API + Tauri)
just dev

# Run tests
just test

# Tauri desktop app
just tauri-dev

# CLI
just cli
```

## Requirements

- Python 3.11+
- Node.js 20+
- pnpm 8+
- Rust (for Tauri)
- uv (Python package manager)
- just (task runner)
