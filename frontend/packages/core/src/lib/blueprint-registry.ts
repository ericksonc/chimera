/**
 * Static blueprint registry - works in both web and desktop modes
 * Blueprints are registered at import time, no filesystem access needed
 */

export interface BlueprintDefinition {
  id: string;
  name: string;
  description?: string;
  /** The raw blueprint JSON content */
  blueprintJson: string;
}

export const blueprintRegistry: BlueprintDefinition[] = [];

export function registerBlueprint(blueprint: BlueprintDefinition) {
  // Avoid duplicates
  if (!blueprintRegistry.find((b) => b.id === blueprint.id)) {
    blueprintRegistry.push(blueprint);
    console.log(`[BlueprintRegistry] Registered blueprint: ${blueprint.name}`);
  }
}

export function getBlueprint(id: string): BlueprintDefinition | undefined {
  return blueprintRegistry.find((b) => b.id === id);
}

export function listBlueprints(): BlueprintDefinition[] {
  return blueprintRegistry;
}
