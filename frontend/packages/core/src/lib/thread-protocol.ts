/**
 * ThreadProtocol v0.0.7 - Event types for conversation persistence
 *
 * ThreadProtocol IS condensed VSP - we accumulate streaming deltas into complete
 * events but otherwise preserve VSP v6 format exactly.
 *
 * Key principles:
 * - VSP v6 event types with hyphens (e.g., "user-message", "tool-input-available")
 * - VSP field names in camelCase (e.g., agentId, toolCallId)
 * - Tool args/results as objects (not JSON strings)
 * - Message boundaries via data-agent-start/finish (custom events)
 * - All custom events use "data-*" prefix with data in "data" field
 * - Condensed types: text-complete, reasoning-complete
 *
 * Official spec: /Users/ericksonc/appdev/chimera/meta/designdocs/threadprotocol/rc7/thread_protocol_v007.md
 */

/** Base event structure */
export interface ThreadProtocolEvent {
  type: string;
  timestamp?: string;
  [key: string]: any;
}

/** Thread-level events */
export interface ThreadStartEvent extends ThreadProtocolEvent {
  type: "thread-start";
  threadId: string;
  parentThreadId?: string | null;
  configuration?: any;
}

export interface ThreadEndEvent extends ThreadProtocolEvent {
  type: "thread-end";
  threadId: string;
}

export interface ThreadBlueprintEvent extends ThreadProtocolEvent {
  type: "thread-blueprint";
  threadId: string;
  version: string;
  blueprint: any;
}

/** Turn boundary events (v0.0.7: custom data-* events) */
export interface DataAgentStartEvent extends ThreadProtocolEvent {
  type: "data-agent-start";
  data: {
    agentId: string;
    agentName: string;
  };
  threadId?: string;
}

export interface DataAgentFinishEvent extends ThreadProtocolEvent {
  type: "data-agent-finish";
  data: {
    agentId: string;
    agentName?: string;
  };
  threadId?: string;
}

/** Message boundary events (VSP) */
export interface MessageStartEvent extends ThreadProtocolEvent {
  type: "start";
  messageId: string;
}

export interface MessageFinishEvent extends ThreadProtocolEvent {
  type: "finish";
}

/** Message events (VSP-compatible) */
export interface UserMessageEvent extends ThreadProtocolEvent {
  type: "user-message";
  content: string;
}

/** Condensed content events (v0.0.7) */
export interface TextCompleteEvent extends ThreadProtocolEvent {
  type: "text-complete";
  id: string;  // VSP's text block ID
  text: string;
  providerMetadata?: Record<string, unknown>;
}

export interface ReasoningCompleteEvent extends ThreadProtocolEvent {
  type: "reasoning-complete";
  id: string;  // VSP's reasoning block ID
  text: string;
  providerMetadata?: Record<string, unknown>;
}

/** Tool events (VSP v6 format) */
export interface ToolInputAvailableEvent extends ThreadProtocolEvent {
  type: "tool-input-available";
  toolCallId: string;
  toolName: string;
  input: any;  // Structured object, not JSON string
  title?: string;
  dynamic?: boolean;
  providerExecuted?: boolean;
  providerMetadata?: Record<string, unknown>;
}

export interface ToolOutputAvailableEvent extends ThreadProtocolEvent {
  type: "tool-output-available";
  toolCallId: string;
  output: any;  // Structured object
  preliminary?: boolean;
  providerMetadata?: Record<string, unknown>;
}

/** Tool approval events (v6) */
export interface ToolApprovalRequestEvent extends ThreadProtocolEvent {
  type: "tool-approval-request";
  approvalId: string;
  toolCallId: string;
}

export interface ToolOutputDeniedEvent extends ThreadProtocolEvent {
  type: "tool-output-denied";
  toolCallId: string;
}

/** Tool error events (v6) */
export interface ToolInputErrorEvent extends ThreadProtocolEvent {
  type: "tool-input-error";
  toolCallId: string;
  toolName: string;
  input: any;
  errorText: string;
  providerExecuted?: boolean;
  providerMetadata?: Record<string, unknown>;
  dynamic?: boolean;
  title?: string;
}

export interface ToolOutputErrorEvent extends ThreadProtocolEvent {
  type: "tool-output-error";
  toolCallId: string;
  errorText: string;
  providerExecuted?: boolean;
  dynamic?: boolean;
}

/** Step boundaries (VSP) */
export interface StepStartEvent extends ThreadProtocolEvent {
  type: "start-step";
  stepNumber?: number;
}

export interface StepEndEvent extends ThreadProtocolEvent {
  type: "finish-step";
  stepNumber?: number;
}

/** System events */
export interface ErrorEvent extends ThreadProtocolEvent {
  type: "error";
  errorText: string;
  errorCode?: string;
}

export interface UsageEvent extends ThreadProtocolEvent {
  type: "data-sys-usage";
  data: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
  };
  stepNumber?: number;
}

/** Custom Chimera events (v0.0.7: data nested in "data" field) */
export interface ChimeraMutationEvent extends ThreadProtocolEvent {
  type: "data-app-chimera";
  data: {
    source: string; // e.g., "widget:TodoWidget:inst1" or "space:GroupChatSpace:inst1"
    payload: any;   // Component-specific mutation data
  };
  transient?: boolean;
}

/** Union type of all ThreadProtocol events */
export type ThreadProtocolEventType =
  | ThreadStartEvent
  | ThreadEndEvent
  | ThreadBlueprintEvent
  | DataAgentStartEvent
  | DataAgentFinishEvent
  | MessageStartEvent
  | MessageFinishEvent
  | UserMessageEvent
  | TextCompleteEvent
  | ReasoningCompleteEvent
  | ToolInputAvailableEvent
  | ToolOutputAvailableEvent
  | ToolApprovalRequestEvent
  | ToolOutputDeniedEvent
  | ToolInputErrorEvent
  | ToolOutputErrorEvent
  | StepStartEvent
  | StepEndEvent
  | ErrorEvent
  | UsageEvent
  | ChimeraMutationEvent;

/** Helper to add timestamp to events */
export function addTimestamp<T extends ThreadProtocolEvent>(event: T): T {
  return {
    ...event,
    timestamp: event.timestamp || new Date().toISOString(),
  };
}

/** Check if event is a VSP streaming event (needs accumulation) */
export function isStreamingEvent(type: string): boolean {
  return type.includes("-start") || type.includes("-delta") || type.includes("-end");
}

/** Check if event is a complete event (write to JSONL) */
export function isCompleteEvent(type: string): boolean {
  return !type.includes("-delta") && !type.includes("-start");
}

/** Check if event is a custom Chimera event */
export function isChimeraEvent(type: string): boolean {
  return type.startsWith("data-app-");
}
