import type {
  StorageAdapter,
  ThreadMetadata,
  ThreadProtocolEvent,
  BlueprintMetadata,
} from "@chimera/platform";

export class WebStorageAdapter implements StorageAdapter {
  async loadThread(threadId: string): Promise<ThreadProtocolEvent[]> {
    const key = `thread:${threadId}`;
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : [];
  }

  async appendThreadEvents(
    threadId: string,
    events: ThreadProtocolEvent[]
  ): Promise<void> {
    const key = `thread:${threadId}`;
    const existing = await this.loadThread(threadId);
    const updated = [...existing, ...events];
    localStorage.setItem(key, JSON.stringify(updated));
  }

  async listThreads(): Promise<ThreadMetadata[]> {
    const threads: ThreadMetadata[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("thread:")) {
        const id = key.replace("thread:", "");
        // We need to peek at the first event to get metadata if possible, or just use defaults
        // For efficiency, we might just use defaults for the list view
        threads.push({
          thread_id: id,
          title: id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          file_path: "",
        });
      }
    }
    return threads;
  }

  async createThread(blueprintJson: string): Promise<string> {
    const id = crypto.randomUUID();
    const key = `thread:${id}`;

    // Parse blueprint to get initial event
    let blueprintEvent;
    try {
      const parsed = JSON.parse(blueprintJson);
      blueprintEvent = {
        type: "thread-blueprint",
        timestamp: new Date().toISOString(),
        threadId: id,
        threadProtocolVersion: "0.0.7",
        blueprintVersion: "0.0.7",
        blueprint: parsed.blueprint || parsed, // Handle both wrapped and unwrapped
      };
    } catch (e) {
      console.error("Failed to parse blueprint JSON", e);
      blueprintEvent = { type: "thread-blueprint", data: {} };
    }

    // Save initial thread state
    localStorage.setItem(key, JSON.stringify([blueprintEvent]));
    return id;
  }

  async listBlueprints(): Promise<BlueprintMetadata[]> {
    // TODO: Add your experimental blueprints here
    return [];
    /* Example:
    return [
      {
        id: "test-agent",
        name: "Test Agent",
        description: "A test agent",
        file_path: "test-agent.json"
      }
    ];
    */
  }

  async readBlueprint(_filePath: string): Promise<string> {
    // TODO: Return the JSON content of your blueprint
    // Since the browser cannot read files from disk, you must copy/paste the blueprint JSON here.
    return "";
    /* Example:
    if (filePath === "test-agent.json") {
      return JSON.stringify({
        "type": "thread-blueprint",
        ... (paste full JSON content here)
      });
    }
    */
  }
}
