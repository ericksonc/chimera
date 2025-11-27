import { useEffect, useState } from "react";
import { useThreadStore } from "@chimera/core/stores/threadStore";
import { useBlueprintStore } from "@chimera/core/stores/blueprintStore";
import { useAdapters } from "@chimera/core/providers/AdapterProvider";
import { ChimeraTransport } from "@chimera/core/lib/chimera-transport";
import { hydrateFromEvents } from "@chimera/core/lib/jsonl-hydrator";
import type { UIMessage } from "ai";

import { Shell } from "./components/Shell";
import { CwdSelector } from "./components/CwdSelector";
import { Artifact } from "./components/Artifact";
import { Chat } from "./components/Chat";
import { ThreadList } from "@chimera/core/components/ThreadList";

function App() {
  const { currentThread, createThread } = useThreadStore();
  const { blueprints, loadBlueprints } = useBlueprintStore();
  const { storageAdapter, configProvider } = useAdapters();

  const [cwd, setCwd] = useState("/Users/ericksonc/appdev/chimera-desktop"); // Default for dev
  const [transport, setTransport] = useState<ChimeraTransport | null>(null);
  const [initialMessages, setInitialMessages] = useState<UIMessage[]>([]);

  // 1. Load blueprints on mount
  useEffect(() => {
    loadBlueprints();
  }, [loadBlueprints]);

  // 2. Hardcode kimi-engineer blueprint selection if no thread
  useEffect(() => {
    const init = async () => {
      if (!currentThread && blueprints.length > 0) {
        const kimiBlueprint = blueprints.find((b) => b.id === "kimi-engineer");
        if (kimiBlueprint) {
          console.log("Auto-creating thread with kimi-engineer blueprint");
          // We need to read the blueprint content first
          // Since we don't have direct access to readBlueprint from store (it's not exposed),
          // we can use the storageAdapter directly if we had it, but we only have it via useAdapters.
          // Wait, useAdapters gives us storageAdapter!

          try {
            const content = await storageAdapter.readBlueprint(
              kimiBlueprint.file_path
            );
            await createThread(content);
          } catch (err) {
            console.error("Failed to read blueprint or create thread:", err);
          }
        }
      }
    };
    init();
  }, [currentThread, blueprints, createThread, storageAdapter]);

  // 3. Initialize transport when thread changes
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
      });

      await newTransport.loadHistory();

      const threadProtocol = newTransport.getThreadProtocol();
      if (threadProtocol.length > 0) {
        const events = threadProtocol.slice(1);
        const hydrated = hydrateFromEvents(events);
        setInitialMessages(hydrated);
      } else {
        setInitialMessages([]);
      }

      setTransport(newTransport);
    };

    initTransport();
  }, [currentThread, configProvider, storageAdapter]);

  return (
    <Shell
      header={
        <div className="flex items-center justify-between w-full">
          <div className="font-semibold">Experimental Layout</div>
          <CwdSelector value={cwd} onChange={setCwd} />
        </div>
      }
      sidebar={
        <div className="h-full flex flex-col">
          <div className="p-4 font-medium border-b">Past Threads</div>
          <div className="flex-1 overflow-auto">
            <ThreadList />
          </div>
        </div>
      }
      main={
        transport && currentThread ? (
          <Chat
            transport={transport}
            currentThread={currentThread}
            initialMessages={initialMessages}
            cwd={cwd}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            Initializing...
          </div>
        )
      }
      aside={<Artifact />}
    />
  );
}

export default App;
