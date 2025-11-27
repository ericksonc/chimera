import { invoke } from "@tauri-apps/api/core";
import type {
  StorageAdapter,
  ThreadMetadata,
  BlueprintMetadata,
  ThreadProtocolEvent,
} from "@chimera/platform";

/**
 * Tauri implementation of StorageAdapter
 * Uses Tauri's invoke API to call Rust commands for file operations
 */
export class TauriStorageAdapter implements StorageAdapter {
  async listThreads(): Promise<ThreadMetadata[]> {
    return invoke<ThreadMetadata[]>("list_threads");
  }

  async createThread(blueprintJson: string): Promise<string> {
    return invoke<string>("create_thread", { blueprintJson });
  }

  async loadThread(threadId: string): Promise<ThreadProtocolEvent[]> {
    return invoke<ThreadProtocolEvent[]>("load_thread", { threadId });
  }

  async appendThreadEvents(
    threadId: string,
    events: ThreadProtocolEvent[]
  ): Promise<void> {
    await invoke("append_thread_events", { threadId, events });
  }

  async listBlueprints(): Promise<BlueprintMetadata[]> {
    return invoke<BlueprintMetadata[]>("list_blueprints");
  }

  async readBlueprint(filePath: string): Promise<string> {
    return invoke<string>("read_blueprint", { filePath });
  }
}
