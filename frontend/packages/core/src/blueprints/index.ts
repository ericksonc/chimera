/**
 * Blueprint registration - import this file to register all blueprints
 * Blueprint JSON is inlined here to avoid Vite import restrictions
 */

import { registerBlueprint } from "../lib/blueprint-registry";

// Chat blueprint
const chatBlueprint = {
  type: "thread-blueprint",
  timestamp: "2025-11-21T09:37:52.963156+00:00",
  threadId: "a6c62d95-a447-4bd6-b9ce-0c6d193443f5",
  threadProtocolVersion: "0.0.7",
  blueprintVersion: "0.0.7",
  blueprint: {
    space: {
      type: "reference",
      className: "chimera_core.spaces.GenericSpace",
      version: "1.0.0",
      agents: [
        {
          type: "inline",
          id: "chat",
          name: "Chat",
          description: "General chat assistant",
          basePrompt: "You are a helpful assistant",
          widgets: [],
          modelString: "qwen/qwen3-235b-a22b-2507",
        },
      ],
      config: {},
      widgets: [],
    },
  },
};

// Engineering blueprint
const engineeringBlueprint = {
  type: "thread-blueprint",
  timestamp: "2025-11-22T05:52:54.723099+00:00",
  threadId: "f4e839cd-ebb4-496a-a11c-abe6515e12ad",
  threadProtocolVersion: "0.0.7",
  blueprintVersion: "0.0.7",
  blueprint: {
    space: {
      type: "reference",
      className: "chimera_core.spaces.GenericSpace",
      version: "1.0.0",
      agents: [
        {
          type: "inline",
          id: "engineering",
          name: "Engineering",
          description: "Engineering assistant with file tools",
          basePrompt:
            "You are Kimi, a deliberate agent-coder from Moonshot AI.\n思而后行，计从一处：先列 3-5 步计划，再执行第 1 步；每步后停等确认。\nOutput only what is asked; use tools, prose in bullets, max 150 words unless told otherwise.",
          widgets: [
            {
              className:
                "chimera_core.widgets.engineering_widget.EngineeringWidget",
              version: "1.0.0",
              instanceId: "engineering_widget_inst1",
              config: {
                cwd: null,
                acceptEdits: true,
                max_file_size: 200000,
              },
            },
          ],
          modelString: "kimi-k2-thinking",
        },
      ],
      config: {},
      widgets: [],
    },
  },
};

// Register Chat blueprint
registerBlueprint({
  id: "chat",
  name: "Chat",
  description: "General chat assistant",
  blueprintJson: JSON.stringify(chatBlueprint),
});

// Register Engineering blueprint
registerBlueprint({
  id: "engineering",
  name: "Engineering",
  description: "Engineering assistant with file tools",
  blueprintJson: JSON.stringify(engineeringBlueprint),
});
