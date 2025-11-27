/**
 * Platform adapter interfaces for Chimera
 * These abstract platform-specific operations (Tauri, Web, etc.)
 */

/**
 * Thread metadata returned by storage operations
 * Matches Rust backend ThreadMetadata structure
 */
export interface ThreadMetadata {
  thread_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  file_path: string;
}

/**
 * Blueprint metadata
 */
export interface BlueprintMetadata {
  id: string;
  name: string;
  description?: string;
  file_path: string;
}

/**
 * Thread protocol event (from JSONL)
 * Note: Uses VSP v6 event format with 'type' field
 */
export interface ThreadProtocolEvent {
  type: string;
  timestamp?: string;
  [key: string]: any;
}

/**
 * Storage adapter - abstracts file system operations
 * Implementation: Tauri (local JSONL files), Web (IndexedDB, API, etc.)
 */
export interface StorageAdapter {
  /**
   * List all conversation threads
   */
  listThreads(): Promise<ThreadMetadata[]>;

  /**
   * Create a new thread
   */
  createThread(blueprintJson: string): Promise<string>;

  /**
   * Load thread events from storage
   */
  loadThread(threadId: string): Promise<ThreadProtocolEvent[]>;

  /**
   * Append events to a thread
   */
  appendThreadEvents(
    threadId: string,
    events: ThreadProtocolEvent[]
  ): Promise<void>;

  /**
   * List available agent blueprints
   */
  listBlueprints(): Promise<BlueprintMetadata[]>;

  /**
   * Read a blueprint file
   */
  readBlueprint(filePath: string): Promise<string>;
}

/**
 * Configuration provider - platform-specific config
 * Implementation: Tauri (Rust commands), Web (env vars, runtime config)
 */
export interface ConfigProvider {
  /**
   * Get the Python backend URL
   */
  getBackendUrl(): Promise<string>;

  /**
   * Get platform identifier
   */
  getPlatform(): 'desktop' | 'web';
}

/**
 * Theme event listener - OS/browser theme changes
 * Implementation: Tauri (event listener), Web (matchMedia)
 */
export interface ThemeEventListener {
  /**
   * Start listening for theme changes
   * @param callback Function to call when theme changes
   * @returns Cleanup function to stop listening
   */
  listen(callback: (theme: 'light' | 'dark') => void): () => void;
}
