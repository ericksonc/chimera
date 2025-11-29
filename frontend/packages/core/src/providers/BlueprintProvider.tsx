import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  blueprintRegistry,
  type BlueprintDefinition,
} from "../lib/blueprint-registry";

// Import blueprints to trigger registration
import "../blueprints";

interface BlueprintContextValue {
  currentBlueprintId: string | null;
  setCurrentBlueprintId: (id: string) => void;
  blueprints: BlueprintDefinition[];
  currentBlueprint: BlueprintDefinition | null;
}

const BlueprintContext = createContext<BlueprintContextValue | null>(null);

interface BlueprintProviderProps {
  children: ReactNode;
  defaultBlueprintId?: string;
}

export function BlueprintProvider({
  children,
  defaultBlueprintId,
}: BlueprintProviderProps) {
  const [currentBlueprintId, setCurrentBlueprintIdState] = useState<
    string | null
  >(defaultBlueprintId ?? null);

  // Set default blueprint on mount - prefer "chat" if available
  useEffect(() => {
    if (blueprintRegistry.length > 0 && !currentBlueprintId) {
      const chatBlueprint = blueprintRegistry.find((b) => b.id === "chat");
      setCurrentBlueprintIdState(chatBlueprint?.id ?? blueprintRegistry[0].id);
    }
  }, [currentBlueprintId]);

  const setCurrentBlueprintId = useCallback((id: string) => {
    setCurrentBlueprintIdState(id);
    console.log("[BlueprintProvider] Set current blueprint:", id);
  }, []);

  const currentBlueprint =
    blueprintRegistry.find((b) => b.id === currentBlueprintId) ?? null;

  return (
    <BlueprintContext.Provider
      value={{
        currentBlueprintId,
        setCurrentBlueprintId,
        blueprints: blueprintRegistry,
        currentBlueprint,
      }}
    >
      {children}
    </BlueprintContext.Provider>
  );
}

export function useBlueprint() {
  const context = useContext(BlueprintContext);
  if (!context) {
    throw new Error("useBlueprint must be used within a BlueprintProvider");
  }
  return context;
}
