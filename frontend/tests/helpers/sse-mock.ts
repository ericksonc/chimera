/**
 * SSE Mock Helper - Creates mock SSE streams for testing ChimeraTransport.
 *
 * Key insight: ChimeraTransport processes SSE "data: {...}\n\n" lines.
 * This helper creates ReadableStreams that emit VSP events in that format.
 */

import type { ThreadProtocolEvent } from "../../packages/core/src/lib/thread-protocol";

/**
 * Create a mock SSE stream from VSP events.
 * Returns a Response-like object with a body ReadableStream.
 */
export function createMockSSEStream(
  events: Array<Record<string, unknown>>
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  // Build full SSE payload upfront
  let payload = "";
  for (const event of events) {
    payload += `data: ${JSON.stringify(event)}\n\n`;
  }
  payload += "data: [DONE]\n\n";

  const data = encoder.encode(payload);
  let sent = false;

  return new ReadableStream({
    start(controller) {
      // Enqueue all data at once and close immediately
      controller.enqueue(data);
      controller.close();
    },
  });
}

/**
 * Create a mock Response for fetch calls.
 */
export function createMockResponse(
  events: Array<Record<string, unknown>>,
  options?: { status?: number; statusText?: string }
): Response {
  const body = createMockSSEStream(events);
  return new Response(body, {
    status: options?.status ?? 200,
    statusText: options?.statusText ?? "OK",
    headers: { "Content-Type": "text/event-stream" },
  });
}

/**
 * VSP Event Builders - Helpers to create properly formatted VSP events.
 * These match the exact format that ChimeraTransport expects.
 */
export const VSP = {
  /** Agent start event */
  agentStart: (agentId: string, agentName: string) => ({
    type: "data-agent-start",
    data: { agentId, agentName },
  }),

  /** Agent finish event */
  agentFinish: (agentId: string, agentName: string) => ({
    type: "data-agent-finish",
    data: { agentId, agentName },
  }),

  /** Text start - begins text accumulation */
  textStart: (id: string) => ({
    type: "text-start",
    id,
  }),

  /** Text delta - streaming text chunk */
  textDelta: (id: string, delta: string) => ({
    type: "text-delta",
    id,
    delta,
  }),

  /** Text end - finalizes text accumulation */
  textEnd: (id: string) => ({
    type: "text-end",
    id,
  }),

  /** User message event */
  userMessage: (content: string) => ({
    type: "user-message",
    content,
  }),

  /** Tool input start - begins tool call accumulation */
  toolInputStart: (toolCallId: string, toolName: string) => ({
    type: "tool-input-start",
    toolCallId,
    toolName,
  }),

  /** Tool input delta - streaming tool args */
  toolInputDelta: (toolCallId: string, inputTextDelta: string) => ({
    type: "tool-input-delta",
    toolCallId,
    inputTextDelta,
  }),

  /** Tool input available - final tool call (may include requiresApproval) */
  toolInputAvailable: (
    toolCallId: string,
    toolName: string,
    input: Record<string, unknown>,
    requiresApproval = false
  ) => ({
    type: "tool-input-available",
    toolCallId,
    toolName,
    input,
    requiresApproval,
  }),

  /** Tool approval request - requires user confirmation */
  toolApprovalRequest: (toolCallId: string, message?: string) => ({
    type: "tool-approval-request",
    toolCallId,
    message,
  }),

  /** Tool output available - tool result */
  toolOutputAvailable: (
    toolCallId: string,
    output: unknown,
    isError = false
  ) => ({
    type: "tool-output-available",
    toolCallId,
    output,
    isError,
  }),

  /** Tool output denied - user rejected tool */
  toolOutputDenied: (toolCallId: string, message?: string) => ({
    type: "tool-output-denied",
    toolCallId,
    message,
  }),

  /** Reasoning start */
  reasoningStart: (id: string) => ({
    type: "reasoning-start",
    id,
  }),

  /** Reasoning delta */
  reasoningDelta: (id: string, delta: string) => ({
    type: "reasoning-delta",
    id,
    delta,
  }),

  /** Reasoning end */
  reasoningEnd: (id: string) => ({
    type: "reasoning-end",
    id,
  }),

  /** Start step boundary */
  startStep: (stepId: string) => ({
    type: "start-step",
    stepId,
  }),

  /** Finish step boundary */
  finishStep: (stepId: string) => ({
    type: "finish-step",
    stepId,
  }),

  /** Stream start */
  start: (messageId: string) => ({
    type: "start",
    messageId,
  }),

  /** Stream finish */
  finish: (messageId: string) => ({
    type: "finish",
    messageId,
  }),
};

/**
 * Scenario Builders - Common event sequences for testing.
 */
export const Scenarios = {
  /** Simple text response: agent says something */
  simpleTextResponse: (
    agentId: string,
    agentName: string,
    textId: string,
    text: string
  ) => [
    VSP.agentStart(agentId, agentName),
    VSP.textStart(textId),
    VSP.textDelta(textId, text),
    VSP.textEnd(textId),
    VSP.agentFinish(agentId, agentName),
  ],

  /** Tool call that doesn't require approval */
  autoApprovedToolCall: (
    agentId: string,
    agentName: string,
    toolCallId: string,
    toolName: string,
    input: Record<string, unknown>,
    output: unknown
  ) => [
    VSP.agentStart(agentId, agentName),
    VSP.toolInputStart(toolCallId, toolName),
    VSP.toolInputDelta(toolCallId, JSON.stringify(input)),
    VSP.toolInputAvailable(toolCallId, toolName, input, false),
    VSP.toolOutputAvailable(toolCallId, output),
    VSP.agentFinish(agentId, agentName),
  ],

  /** Tool call requiring approval */
  toolCallRequiringApproval: (
    agentId: string,
    agentName: string,
    toolCallId: string,
    toolName: string,
    input: Record<string, unknown>
  ) => [
    VSP.agentStart(agentId, agentName),
    VSP.toolInputStart(toolCallId, toolName),
    VSP.toolInputDelta(toolCallId, JSON.stringify(input)),
    VSP.toolInputAvailable(toolCallId, toolName, input, true),
    VSP.toolApprovalRequest(toolCallId),
    // Stream pauses here - user must approve
  ],
};
