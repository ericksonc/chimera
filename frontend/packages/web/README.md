# @chimera/web

Web version of Chimera - **Coming Soon**

## Overview

This package will contain the web implementation of Chimera, sharing the core UI components and business logic from `@chimera/core` while providing web-specific adapters for:

- **Storage**: IndexedDB or cloud API instead of local files
- **Configuration**: Environment variables or runtime config instead of Tauri commands
- **Theme**: Browser matchMedia instead of Tauri events

## Implementation Plan

When ready to implement:

1. Create web-specific adapters in `src/adapters/`:
   - `WebStorageAdapter.ts` - Using IndexedDB or REST API
   - `WebConfigProvider.ts` - Using environment variables
   - `WebThemeListener.ts` - Using `matchMedia`

2. Set up Next.js/Vite app with:
   - Entry point that wires up web adapters
   - Deployment configuration
   - Auth/multi-user support (if needed)

## Architecture

```
packages/web/
├── src/
│   ├── adapters/          # Web-specific adapter implementations
│   ├── app/               # Next.js app or routes
│   └── main.tsx           # Entry point with adapter wiring
├── public/                # Static assets
└── package.json
```

The web version will use the exact same components from `@chimera/core`, just with different adapters injected via `AdapterProvider`.
