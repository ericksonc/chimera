import { useEffect, useState } from "react";
import { ChimeraTransport } from "../lib/chimera-transport";
import { hydrateFromEvents } from "../lib/jsonl-hydrator";
import { useThreadStore } from "../stores/threadStore";
import { useAdapters } from "../providers/AdapterProvider";
import { ChimeraChatInner } from "./ChimeraChatInner";
import type { UIMessage } from "ai";

export function ChimeraChat() {
  const { currentThread } = useThreadStore();
  const { storageAdapter, configProvider } = useAdapters();
  const [transport, setTransport] = useState<ChimeraTransport | null>(null);
  const [initialMessages, setInitialMessages] = useState<UIMessage[]>([]);

  // Initialize transport when thread changes
  useEffect(() => {
    if (!currentThread) {
      setTransport(null);
      setInitialMessages([]);
      return;
    }

    const initTransport = async () => {
      const backendUrl = await configProvider.getBackendUrl();

      const newTransport = new ChimeraTransport({
        threadId: currentThread.metadata.thread_id,
        backendUrl,
        storageAdapter,
        onEventsAccumulated: async (events) => {
          // Events are already persisted by ChimeraTransport
          // Just log for now
          console.log(`[ChimeraChat] Accumulated ${events.length} events`);
        },
      });

      // Load existing history
      await newTransport.loadHistory();

      // Hydrate JSONL events to UIMessages
      const threadProtocol = newTransport.getThreadProtocol();
      if (threadProtocol.length > 0) {
        // Skip line 0 (blueprint), hydrate the rest
        const events = threadProtocol.slice(1);
        const hydrated = hydrateFromEvents(events);
        console.log(`[ChimeraChat] Hydrated ${hydrated.length} messages from ${events.length} events`);
        setInitialMessages(hydrated);
      } else {
        setInitialMessages([]);
      }

      setTransport(newTransport);
      console.log(`[ChimeraChat] Initialized transport for thread ${currentThread.metadata.thread_id}`);
    };

    initTransport();
  }, [currentThread]);

  if (!currentThread) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center space-y-2">
          <p className="text-lg">No conversation selected</p>
          <p className="text-sm">
            Select an existing thread or create a new one to start chatting
          </p>
        </div>
      </div>
    );
  }

  if (!transport) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p>Loading conversation...</p>
      </div>
    );
  }

  // Only render the inner component when we have both thread and transport
  return (
    <ChimeraChatInner
      transport={transport}
      currentThread={currentThread}
      messages={initialMessages}
    />
  );
}
