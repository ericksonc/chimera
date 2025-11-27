import { useEffect, useState } from "react";
import { useThreadStore } from "@chimera/core/stores/threadStore";
import { useBlueprintStore } from "@chimera/core/stores/blueprintStore";
import { useAdapters } from "@chimera/core/providers/AdapterProvider";
import { Button } from "@chimera/core/components/ui/button";

function App() {
  const { currentThread, createThread } = useThreadStore();
  const { blueprints, loadBlueprints } = useBlueprintStore();
  const { storageAdapter } = useAdapters();
  const [isInitializing, setIsInitializing] = useState(true);

  // 1. Load blueprints on mount
  useEffect(() => {
    loadBlueprints();
  }, [loadBlueprints]);

  // 2. Auto-create thread if we have a blueprint
  useEffect(() => {
    const init = async () => {
      if (!currentThread && blueprints.length > 0) {
        // Example: Auto-create with the first blueprint
        // You can customize this logic to select a specific blueprint
        const defaultBlueprint = blueprints[0];
        if (defaultBlueprint) {
          console.log(
            `Auto-creating thread with ${defaultBlueprint.id} blueprint`
          );
          try {
            const content = await storageAdapter.readBlueprint(
              defaultBlueprint.file_path
            );
            await createThread(content);
          } catch (err) {
            console.error("Failed to create thread:", err);
          }
        }
      }
      setIsInitializing(false);
    };

    init();
  }, [currentThread, blueprints, createThread, storageAdapter]);

  if (isInitializing && blueprints.length > 0 && !currentThread) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        Initializing...
      </div>
    );
  }

  if (!currentThread && blueprints.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-4">
        <h1 className="text-2xl font-bold mb-2">Setup Required</h1>
        <p className="text-muted-foreground mb-4 text-center max-w-md">
          No blueprints found. Please configure{" "}
          <code>src/adapters/WebStorageAdapter.ts</code> to include at least one
          blueprint for your experiment.
        </p>
        <Button variant="outline" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background text-foreground p-4">
      <h1 className="text-4xl font-bold mb-4">Chimera Experimental Template</h1>
      <p className="text-muted-foreground mb-8 text-center max-w-md">
        This is a template for creating new frontend experiments. It comes
        pre-configured with Tailwind CSS, Chimera Core components, and mock
        adapters.
      </p>
      <div className="flex gap-4">
        <Button onClick={() => alert("It works!")}>Test Button</Button>
      </div>
      {currentThread && (
        <div className="mt-8 text-sm text-muted-foreground">
          Active Thread: {currentThread.metadata.thread_id}
        </div>
      )}
    </div>
  );
}

export default App;
