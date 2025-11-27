import { create } from 'zustand';
import type { StorageAdapter, BlueprintMetadata } from '@chimera/platform';

interface BlueprintState {
  blueprints: BlueprintMetadata[];
  selectedBlueprint: BlueprintMetadata | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  loadBlueprints: () => Promise<void>;
  selectBlueprint: (id: string) => void;
  clearSelection: () => void;
}

let storageAdapter: StorageAdapter | null = null;

/**
 * Get the storage adapter with initialization check
 * Throws a descriptive error if not initialized
 */
function getStorageAdapter(): StorageAdapter {
  if (!storageAdapter) {
    throw new Error(
      '[BlueprintStore] storageAdapter not initialized. Call initBlueprintStore() before using the blueprint store.'
    );
  }
  return storageAdapter;
}

/**
 * Initialize the blueprint store with a storage adapter
 * Must be called before using the store
 */
export function initBlueprintStore(adapter: StorageAdapter) {
  storageAdapter = adapter;
}

export const useBlueprintStore = create<BlueprintState>((set, get) => ({
  blueprints: [],
  selectedBlueprint: null,
  isLoading: false,
  error: null,

  loadBlueprints: async () => {
    set({ isLoading: true, error: null });
    try {
      const adapter = getStorageAdapter();
      const blueprints = await adapter.listBlueprints();
      set({ blueprints, isLoading: false });
      console.log(`[BlueprintStore] Loaded ${blueprints.length} blueprints`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      set({ error: errorMessage, isLoading: false });
      console.error('[BlueprintStore] Failed to load blueprints:', error);
    }
  },

  selectBlueprint: (id: string) => {
    const blueprint = get().blueprints.find((b) => b.id === id);
    if (blueprint) {
      set({ selectedBlueprint: blueprint });
      console.log('[BlueprintStore] Selected blueprint:', blueprint.name);
    }
  },

  clearSelection: () => {
    set({ selectedBlueprint: null });
  },
}));
