import { useEffect } from "react";
import { useBlueprintStore } from "../stores/blueprintStore";
import { useThreadStore } from "../stores/threadStore";
import { useAdapters } from "../providers/AdapterProvider";

export function BlueprintSelector() {
  const { storageAdapter } = useAdapters();
  const {
    blueprints,
    selectedBlueprint,
    isLoading,
    error,
    loadBlueprints,
    selectBlueprint,
  } = useBlueprintStore();

  const { createThread } = useThreadStore();

  useEffect(() => {
    loadBlueprints();
  }, [loadBlueprints]);

  const handleCreateThread = async () => {
    if (!selectedBlueprint) return;

    try {
      // Read the blueprint JSON file via adapter
      const blueprintJson = await storageAdapter.readBlueprint(
        selectedBlueprint.file_path
      );

      // Create thread with blueprint
      await createThread(blueprintJson);
    } catch (error) {
      console.error("Failed to create thread:", error);
    }
  };

  if (isLoading) {
    return (
      <div className="p-4">
        <p className="text-sm text-muted-foreground">Loading blueprints...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-destructive">Error: {error}</p>
      </div>
    );
  }

  if (blueprints.length === 0) {
    return (
      <div className="p-4">
        <p className="text-sm text-muted-foreground">
          No blueprints found. Add blueprint files to ~/chimera-desktop/blueprints/
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div>
        <h3 className="text-lg font-semibold mb-2">Select Agent Blueprint</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Choose an agent configuration to start a new conversation
        </p>
      </div>

      <div className="space-y-2">
        {blueprints.map((blueprint) => (
          <button
            key={blueprint.id}
            onClick={() => selectBlueprint(blueprint.id)}
            className={`
              w-full text-left p-3 rounded-lg border transition-colors
              ${
                selectedBlueprint?.id === blueprint.id
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-primary/50"
              }
            `}
          >
            <div className="font-medium">{blueprint.file_path.split('/').pop()}</div>
          </button>
        ))}
      </div>

      {selectedBlueprint && (
        <button
          onClick={handleCreateThread}
          className="
            w-full px-4 py-2 rounded-lg
            bg-primary text-primary-foreground
            hover:bg-primary/90
            transition-colors
          "
        >
          Start Conversation with {selectedBlueprint.file_path.split('/').pop()}
        </button>
      )}
    </div>
  );
}
