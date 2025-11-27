import type { UIMessage, UIMessagePart, UIDataTypes, UITools, ToolUIPart as AiToolUIPart } from "ai";
import type { ThreadProtocolEvent } from "./thread-protocol";

/**
 * JSONL Hydrator - Converts ThreadProtocol v0.0.7 events to UIMessages
 *
 * This implements the hydration algorithm based on Vercel AI SDK v6 patterns.
 * Reference: /Users/ericksonc/appdev/aix/claude/ai/v6/reference_for_jsonl_hydration.md
 *
 * Key principles:
 * - Message boundaries determined by data-agent-start/finish events
 * - Tool parts are updated progressively (match by toolCallId)
 * - Data parts can be updated (match by type + id)
 * - Condensed events (text-complete, reasoning-complete) create parts directly
 */

type ToolUIPart = AiToolUIPart<UITools> & {
  type: string; // "tool-{toolName}" or "dynamic-tool"
  toolCallId: string;
  toolName: string;
  state:
    | "input-streaming"
    | "input-available"
    | "approval-requested"
    | "approval-responded"
    | "output-available"
    | "output-error"
    | "output-denied";
  input?: unknown;
  output?: unknown;
  errorText?: string;
  approval?: {
    id: string;
    approved?: boolean;
    reason?: string;
  };
  title?: string;
  providerExecuted?: boolean;
  callProviderMetadata?: Record<string, unknown>;
  resultProviderMetadata?: Record<string, unknown>;
  preliminary?: boolean;
};

/**
 * Hydrate UIMessages from ThreadProtocol JSONL events
 *
 * @param events - Array of ThreadProtocol events (excluding line 0 blueprint)
 * @returns Array of UIMessages ready for useChat({ initialMessages })
 */
export function hydrateFromEvents(events: ThreadProtocolEvent[]): UIMessage[] {
  const messages: UIMessage[] = [];
  let currentMessage: UIMessage | null = null;
  let messageIdCounter = 0;

  for (const event of events) {
    const eventType = event.type;

    // Message boundaries (multi-agent events)
    if (eventType === "data-agent-start") {
      const agentData = (event as any).data;
      currentMessage = {
        id: `msg-${++messageIdCounter}`,
        role: "assistant",
        parts: [],
        metadata: {
          agentId: agentData.agentId,
          agentName: agentData.agentName,
        },
      };

      // Also add as a part for multi-agent tracking
      currentMessage.parts.push({
        type: "data-agent-start",
        data: agentData,
      } as UIMessagePart<UIDataTypes, UITools>);

      continue;
    }

    if (eventType === "data-agent-finish") {
      if (!currentMessage) {
        console.warn("[Hydrator] data-agent-finish without current message");
        continue;
      }

      const agentData = (event as any).data;
      currentMessage.parts.push({
        type: "data-agent-finish",
        data: agentData,
      } as UIMessagePart<UIDataTypes, UITools>);

      messages.push(currentMessage);
      currentMessage = null;
      continue;
    }

    // Skip events outside message boundaries
    if (!currentMessage) {
      continue;
    }

    // Condensed content events
    if (eventType === "text-complete") {
      const textEvent = event as any;
      currentMessage.parts.push({
        type: "text",
        text: textEvent.text,
        state: "done",
        providerMetadata: textEvent.providerMetadata,
      });
      continue;
    }

    if (eventType === "reasoning-complete") {
      const reasoningEvent = event as any;
      currentMessage.parts.push({
        type: "reasoning",
        text: reasoningEvent.text,
        state: "done",
        providerMetadata: reasoningEvent.providerMetadata,
      });
      continue;
    }

    // Step boundaries
    if (eventType === "start-step") {
      currentMessage.parts.push({
        type: "step-start",
      } as UIMessagePart<UIDataTypes, UITools>);
      continue;
    }

    if (eventType === "finish-step") {
      // finish-step doesn't create a part, just marks end of step
      continue;
    }

    // Tool events - progressive updates
    if (eventType === "tool-input-available") {
      const toolEvent = event as any;
      updateToolPart(currentMessage.parts, {
        toolCallId: toolEvent.toolCallId,
        toolName: toolEvent.toolName,
        state: "input-available",
        input: toolEvent.input,
        dynamic: toolEvent.dynamic,
        providerExecuted: toolEvent.providerExecuted,
        title: toolEvent.title,
        callProviderMetadata: toolEvent.providerMetadata,
      });
      continue;
    }

    if (eventType === "tool-output-available") {
      const toolEvent = event as any;
      const toolPart = findToolPart(currentMessage.parts, toolEvent.toolCallId);
      if (toolPart) {
        toolPart.state = "output-available";
        toolPart.output = toolEvent.output;
        toolPart.preliminary = toolEvent.preliminary;
        if (toolEvent.providerMetadata) {
          toolPart.resultProviderMetadata = toolEvent.providerMetadata;
        }
      } else {
        console.warn(`[Hydrator] tool-output-available for unknown toolCallId: ${toolEvent.toolCallId}`);
      }
      continue;
    }

    if (eventType === "tool-output-error") {
      const toolEvent = event as any;
      const toolPart = findToolPart(currentMessage.parts, toolEvent.toolCallId);
      if (toolPart) {
        toolPart.state = "output-error";
        toolPart.errorText = toolEvent.errorText;
      } else {
        console.warn(`[Hydrator] tool-output-error for unknown toolCallId: ${toolEvent.toolCallId}`);
      }
      continue;
    }

    if (eventType === "tool-output-denied") {
      const toolEvent = event as any;
      const toolPart = findToolPart(currentMessage.parts, toolEvent.toolCallId);
      if (toolPart) {
        toolPart.state = "output-denied";
        if (toolPart.approval) {
          toolPart.approval.approved = false;
        }
      } else {
        console.warn(`[Hydrator] tool-output-denied for unknown toolCallId: ${toolEvent.toolCallId}`);
      }
      continue;
    }

    if (eventType === "tool-approval-request") {
      const toolEvent = event as any;
      const toolPart = findToolPart(currentMessage.parts, toolEvent.toolCallId);
      if (toolPart) {
        toolPart.state = "approval-requested";
        toolPart.approval = {
          id: toolEvent.approvalId,
        };
      } else {
        console.warn(`[Hydrator] tool-approval-request for unknown toolCallId: ${toolEvent.toolCallId}`);
      }
      continue;
    }

    // TODO: Source and file events (not needed yet)
    // if (eventType === "source-url") { ... }
    // if (eventType === "source-document") { ... }
    // if (eventType === "file") { ... }

    // Custom data-* events
    if (eventType.startsWith("data-")) {
      // TODO: Future - interpret data-app-chimera and other custom events
      // For now, just add them as parts so they're preserved when sending to server
      processDataEvent(currentMessage.parts, event as any);
      continue;
    }

    // Unknown event type - log but continue
    console.warn(`[Hydrator] Unknown event type: ${eventType}`);
  }

  return messages;
}

/**
 * Find existing tool part by toolCallId
 */
function findToolPart(parts: UIMessagePart<UIDataTypes, UITools>[], toolCallId: string): ToolUIPart | undefined {
  for (const part of parts) {
    const toolPart = part as any;
    if (toolPart.toolCallId === toolCallId) {
      return toolPart as ToolUIPart;
    }
  }
  return undefined;
}

/**
 * Create or update tool part
 *
 * Follows SDK pattern: find by toolCallId and update in place,
 * or create new part if not found.
 */
function updateToolPart(
  parts: UIMessagePart<UIDataTypes, UITools>[],
  options: {
    toolCallId: string;
    toolName: string;
    state: ToolUIPart["state"];
    input: unknown;
    dynamic?: boolean;
    providerExecuted?: boolean;
    title?: string;
    callProviderMetadata?: Record<string, unknown>;
  }
): ToolUIPart {
  let toolPart = findToolPart(parts, options.toolCallId);

  if (!toolPart) {
    // Create new tool part
    const partType = options.dynamic ? "dynamic-tool" : `tool-${options.toolName}`;

    toolPart = {
      type: partType,
      toolCallId: options.toolCallId,
      toolName: options.toolName,
      state: options.state,
      input: options.input,
    } as ToolUIPart;

    parts.push(toolPart as UIMessagePart<UIDataTypes, UITools>);
  }

  // Update fields
  toolPart.state = options.state;
  toolPart.input = options.input;

  if (options.title !== undefined) {
    toolPart.title = options.title;
  }
  if (options.providerExecuted !== undefined) {
    toolPart.providerExecuted = options.providerExecuted;
  }
  if (options.callProviderMetadata !== undefined) {
    toolPart.callProviderMetadata = options.callProviderMetadata;
  }

  return toolPart;
}

/**
 * Process custom data-* events
 *
 * Updates existing part if id matches, otherwise creates new part.
 * Skips transient events (though they shouldn't be in JSONL anyway).
 */
function processDataEvent(parts: UIMessagePart<UIDataTypes, UITools>[], event: any): void {
  // Skip transient events (shouldn't be in JSONL anyway)
  if (event.transient) {
    return;
  }

  // Try to find existing part by type AND id
  let existingPart: any = undefined;
  if (event.id !== undefined) {
    for (const part of parts) {
      const dataPart = part as any;
      if (dataPart.type === event.type && dataPart.id === event.id) {
        existingPart = dataPart;
        break;
      }
    }
  }

  if (existingPart) {
    // Update existing part
    existingPart.data = event.data;
  } else {
    // Create new part
    parts.push({
      type: event.type,
      id: event.id,
      data: event.data,
    } as UIMessagePart<UIDataTypes, UITools>);
  }
}
