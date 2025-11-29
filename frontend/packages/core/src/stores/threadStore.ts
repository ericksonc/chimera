import { create } from "zustand";
import type { StorageAdapter, ThreadMetadata } from "@chimera/platform";
import type { ThreadProtocolEvent } from "../lib/thread-protocol";

// Re-export ThreadMetadata for backwards compatibility
export type { ThreadMetadata };

interface Thread {
  metadata: ThreadMetadata;
  events: ThreadProtocolEvent[];
}

interface ThreadState {
  threads: ThreadMetadata[];
  currentThread: Thread | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  loadThreads: () => Promise<void>;
  createThread: (blueprintJson: string) => Promise<string>;
  loadThread: (threadId: string) => Promise<void>;
  clearCurrentThread: () => void;
  appendEvents: (events: ThreadProtocolEvent[]) => Promise<void>;
  updateThreadTitle: (threadId: string, title: string) => Promise<void>;
}

let storageAdapter: StorageAdapter | null = null;

/**
 * Get the storage adapter with initialization check
 * Throws a descriptive error if not initialized
 */
function getStorageAdapter(): StorageAdapter {
  if (!storageAdapter) {
    throw new Error(
      "[ThreadStore] storageAdapter not initialized. Call initThreadStore() before using the thread store."
    );
  }
  return storageAdapter;
}

/**
 * Initialize the thread store with a storage adapter
 * Must be called before using the store
 */
export function initThreadStore(adapter: StorageAdapter) {
  storageAdapter = adapter;
}

export const useThreadStore = create<ThreadState>((set, get) => ({
  threads: [],
  currentThread: null,
  isLoading: false,
  error: null,

  loadThreads: async () => {
    set({ isLoading: true, error: null });
    try {
      const adapter = getStorageAdapter();
      const threads = await adapter.listThreads();
      set({ threads, isLoading: false });
      console.log(`[ThreadStore] Loaded ${threads.length} threads`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      set({ error: errorMessage, isLoading: false });
      console.error("[ThreadStore] Failed to load threads:", error);
    }
  },

  createThread: async (blueprintJson: string) => {
    set({ isLoading: true, error: null });
    try {
      const adapter = getStorageAdapter();
      const threadId = await adapter.createThread(blueprintJson);
      console.log(`[ThreadStore] Created thread: ${threadId}`);

      // Load the newly created thread
      await get().loadThread(threadId);

      // Refresh thread list
      await get().loadThreads();

      set({ isLoading: false });
      return threadId;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      set({ error: errorMessage, isLoading: false });
      console.error("[ThreadStore] Failed to create thread:", error);
      throw error;
    }
  },

  loadThread: async (threadId: string) => {
    set({ isLoading: true, error: null });
    try {
      const adapter = getStorageAdapter();
      const events = await adapter.loadThread(threadId);

      // Find metadata
      const threads = get().threads;
      const metadata = threads.find((t) => t.thread_id === threadId);

      if (!metadata) {
        // Refresh thread list and try again
        await get().loadThreads();
        const updatedThreads = get().threads;
        const updatedMetadata = updatedThreads.find(
          (t) => t.thread_id === threadId
        );

        if (!updatedMetadata) {
          throw new Error(`Thread metadata not found for ${threadId}`);
        }

        set({
          currentThread: { metadata: updatedMetadata, events },
          isLoading: false,
        });
      } else {
        set({
          currentThread: { metadata, events },
          isLoading: false,
        });
      }

      console.log(
        `[ThreadStore] Loaded thread ${threadId} with ${events.length} events`
      );
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      set({ error: errorMessage, isLoading: false });
      console.error("[ThreadStore] Failed to load thread:", error);
      throw error;
    }
  },

  clearCurrentThread: () => {
    set({ currentThread: null });
  },

  appendEvents: async (events: ThreadProtocolEvent[]) => {
    const current = get().currentThread;
    if (!current) {
      console.warn("[ThreadStore] No current thread to append events to");
      return;
    }

    try {
      const threadId = current.metadata.thread_id;
      const adapter = getStorageAdapter();
      await adapter.appendThreadEvents(threadId, events);

      // Update in-memory events only if we're still on the same thread
      set((state) => {
        if (
          !state.currentThread ||
          state.currentThread.metadata.thread_id !== threadId
        ) {
          // Thread was switched while we were appending, don't update
          return state;
        }
        return {
          currentThread: {
            ...state.currentThread,
            events: [...state.currentThread.events, ...events],
          },
        };
      });

      console.log(
        `[ThreadStore] Appended ${events.length} events to thread ${threadId}`
      );
    } catch (error) {
      console.error("[ThreadStore] Failed to append events:", error);
      throw error;
    }
  },

  updateThreadTitle: async (threadId: string, title: string) => {
    try {
      const adapter = getStorageAdapter();
      await adapter.updateThreadTitle(threadId, title);

      // Update in-memory state
      set((state) => {
        // Update threads list
        const updatedThreads = state.threads.map((t) =>
          t.thread_id === threadId ? { ...t, title } : t
        );

        // Update currentThread if it matches
        const updatedCurrentThread =
          state.currentThread?.metadata.thread_id === threadId
            ? {
                ...state.currentThread,
                metadata: { ...state.currentThread.metadata, title },
              }
            : state.currentThread;

        return {
          threads: updatedThreads,
          currentThread: updatedCurrentThread,
        };
      });

      console.log(`[ThreadStore] Updated title for thread ${threadId}: ${title}`);
    } catch (error) {
      console.error("[ThreadStore] Failed to update thread title:", error);
      throw error;
    }
  },
}));
