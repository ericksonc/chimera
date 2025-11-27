import type {
  StorageAdapter,
  ThreadMetadata,
  ThreadProtocolEvent,
  BlueprintMetadata,
} from '@chimera/platform';

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
      if (key?.startsWith('thread:')) {
        const id = key.replace('thread:', '');
        threads.push({
          thread_id: id,
          title: id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          file_path: '',
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
        type: 'thread-blueprint',
        timestamp: new Date().toISOString(),
        threadId: id,
        threadProtocolVersion: '0.0.7',
        blueprintVersion: '0.0.7',
        blueprint: parsed.blueprint || parsed, // Handle both wrapped and unwrapped
      };
    } catch (e) {
      console.error('Failed to parse blueprint JSON', e);
      blueprintEvent = { type: 'thread-blueprint', data: {} };
    }

    // Save initial thread state
    localStorage.setItem(key, JSON.stringify([blueprintEvent]));
    return id;
  }

  async listBlueprints(): Promise<BlueprintMetadata[]> {
    return [
      {
        id: 'kimi-engineer',
        name: 'Kimi Engineer',
        description: 'A helpful coding assistant',
        file_path: 'kimi-engineer.json',
      },
    ];
  }

  async readBlueprint(filePath: string): Promise<string> {
    if (filePath === 'kimi-engineer.json') {
      return JSON.stringify({
        type: 'thread-blueprint',
        timestamp: '2025-11-22T05:52:54.723099+00:00',
        threadId: 'f4e839cd-ebb4-496a-a11c-abe6515e12ad',
        threadProtocolVersion: '0.0.7',
        blueprintVersion: '0.0.7',
        blueprint: {
          space: {
            type: 'reference',
            className: 'chimera_core.spaces.GenericSpace',
            version: '1.0.0',
            agents: [
              {
                type: 'inline',
                id: 'kimi-engineer',
                name: 'Kimi Engineer',
                description: 'Kimi as Engineer',
                basePrompt:
                  'You are Kimi, a deliberate agent-coder from Moonshot AI.\n\u601d\u800c\u540e\u884c\uff0c\u8ba1\u4ece\u4e00\u5904\uff1a\u5148\u5217 3-5 \u6b65\u8ba1\u5212\uff0c\u518d\u6267\u884c\u7b2c 1 \u6b65\uff1b\u6bcf\u6b65\u540e\u505c\u7b49\u786e\u8ba4\u3002\nOutput only what is asked; use tools, prose in bullets, max 150 words unless told otherwise.',
                widgets: [
                  {
                    className:
                      'chimera_core.widgets.engineering_widget.EngineeringWidget',
                    version: '1.0.0',
                    instanceId: 'engineering_widget_inst1',
                    config: {
                      cwd: null,
                      acceptEdits: true,
                      max_file_size: 200000,
                    },
                  },
                ],
                modelString: 'kimi-k2-thinking',
              },
            ],
            config: {},
            widgets: [],
          },
        },
      });
    }
    return '{}';
  }
}
