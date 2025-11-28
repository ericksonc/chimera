/**
 * Tests for jsonl-hydrator - ThreadProtocol events to UIMessages conversion.
 *
 * The hydrator reconstitutes chat history from persisted ThreadProtocol events
 * for use with Vercel AI SDK's useChat({ initialMessages }).
 */

import { describe, it, expect } from "vitest";
import { hydrateFromEvents } from "../../packages/core/src/lib/jsonl-hydrator";
import type { ThreadProtocolEvent } from "../../packages/core/src/lib/thread-protocol";

/**
 * ThreadProtocol Event Builders - create properly formatted events for testing.
 * These match what ChimeraTransport persists to JSONL.
 */
const Event = {
  agentStart: (agentId: string, agentName: string): ThreadProtocolEvent => ({
    type: "data-agent-start",
    data: { agentId, agentName },
    timestamp: new Date().toISOString(),
  }),

  agentFinish: (agentId: string, agentName: string): ThreadProtocolEvent => ({
    type: "data-agent-finish",
    data: { agentId, agentName },
    timestamp: new Date().toISOString(),
  }),

  // Note: ThreadProtocol spec says 'text', but ChimeraTransport writes 'content'
  // Tests use 'text' to match the spec/hydrator expectation
  textComplete: (id: string, text: string): ThreadProtocolEvent => ({
    type: "text-complete",
    id,
    text,
    timestamp: new Date().toISOString(),
  }),

  reasoningComplete: (id: string, text: string): ThreadProtocolEvent => ({
    type: "reasoning-complete",
    id,
    text,
    timestamp: new Date().toISOString(),
  }),

  toolInputAvailable: (
    toolCallId: string,
    toolName: string,
    input: Record<string, unknown>
  ): ThreadProtocolEvent => ({
    type: "tool-input-available",
    toolCallId,
    toolName,
    input,
    timestamp: new Date().toISOString(),
  }),

  toolOutputAvailable: (
    toolCallId: string,
    output: unknown
  ): ThreadProtocolEvent => ({
    type: "tool-output-available",
    toolCallId,
    output,
    timestamp: new Date().toISOString(),
  }),

  toolOutputError: (
    toolCallId: string,
    errorText: string
  ): ThreadProtocolEvent => ({
    type: "tool-output-error",
    toolCallId,
    errorText,
    timestamp: new Date().toISOString(),
  }),

  toolApprovalRequest: (
    toolCallId: string,
    approvalId?: string
  ): ThreadProtocolEvent => ({
    type: "tool-approval-request",
    toolCallId,
    approvalId: approvalId ?? `approval-${toolCallId}`,
    timestamp: new Date().toISOString(),
  }),

  toolOutputDenied: (toolCallId: string): ThreadProtocolEvent => ({
    type: "tool-output-denied",
    toolCallId,
    timestamp: new Date().toISOString(),
  }),

  startStep: (stepId: string): ThreadProtocolEvent => ({
    type: "start-step",
    stepId,
    timestamp: new Date().toISOString(),
  }),

  finishStep: (stepId: string): ThreadProtocolEvent => ({
    type: "finish-step",
    stepId,
    timestamp: new Date().toISOString(),
  }),

  dataEvent: (
    type: string,
    data: Record<string, unknown>,
    id?: string
  ): ThreadProtocolEvent => ({
    type,
    id,
    data,
    timestamp: new Date().toISOString(),
  }),
};

describe("hydrateFromEvents", () => {
  describe("Message Boundaries", () => {
    it("creates message from agent-start to agent-finish", () => {
      const events = [
        Event.agentStart("jarvis", "Jarvis"),
        Event.textComplete("t1", "Hello!"),
        Event.agentFinish("jarvis", "Jarvis"),
      ];

      const messages = hydrateFromEvents(events);

      expect(messages).toHaveLength(1);
      expect(messages[0].role).toBe("assistant");
      expect(messages[0].metadata?.agentId).toBe("jarvis");
      expect(messages[0].metadata?.agentName).toBe("Jarvis");
    });

    it("creates multiple messages for multiple agent turns", () => {
      const events = [
        // First agent turn
        Event.agentStart("jarvis", "Jarvis"),
        Event.textComplete("t1", "I'll help you."),
        Event.agentFinish("jarvis", "Jarvis"),
        // Second agent turn
        Event.agentStart("jarvis", "Jarvis"),
        Event.textComplete("t2", "Here's more info."),
        Event.agentFinish("jarvis", "Jarvis"),
      ];

      const messages = hydrateFromEvents(events);

      expect(messages).toHaveLength(2);
      expect(messages[0].parts).toHaveLength(3); // agent-start, text, agent-finish
      expect(messages[1].parts).toHaveLength(3);
    });

    it("assigns incremental message IDs", () => {
      const events = [
        Event.agentStart("a1", "Agent 1"),
        Event.textComplete("t1", "First"),
        Event.agentFinish("a1", "Agent 1"),
        Event.agentStart("a2", "Agent 2"),
        Event.textComplete("t2", "Second"),
        Event.agentFinish("a2", "Agent 2"),
      ];

      const messages = hydrateFromEvents(events);

      expect(messages[0].id).toBe("msg-1");
      expect(messages[1].id).toBe("msg-2");
    });

    it("includes agent boundary parts in message", () => {
      const events = [
        Event.agentStart("jarvis", "Jarvis"),
        Event.textComplete("t1", "Hello"),
        Event.agentFinish("jarvis", "Jarvis"),
      ];

      const messages = hydrateFromEvents(events);
      const parts = messages[0].parts;

      expect(parts[0]).toEqual({
        type: "data-agent-start",
        data: { agentId: "jarvis", agentName: "Jarvis" },
      });

      expect(parts[parts.length - 1]).toEqual({
        type: "data-agent-finish",
        data: { agentId: "jarvis", agentName: "Jarvis" },
      });
    });
  });

  describe("Text Content", () => {
    it("creates text part from text-complete event", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.textComplete("text-123", "Hello, world!"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const textPart = messages[0].parts.find((p: any) => p.type === "text");

      expect(textPart).toEqual({
        type: "text",
        text: "Hello, world!",
        state: "done",
        providerMetadata: undefined,
      });
    });

    it("creates reasoning part from reasoning-complete event", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.reasoningComplete("r1", "Let me think about this..."),
        Event.textComplete("t1", "My answer is 42."),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const reasoningPart = messages[0].parts.find(
        (p: any) => p.type === "reasoning"
      );

      expect(reasoningPart).toEqual({
        type: "reasoning",
        text: "Let me think about this...",
        state: "done",
        providerMetadata: undefined,
      });
    });

    it("preserves multiple text parts in order", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.textComplete("t1", "First paragraph."),
        Event.textComplete("t2", "Second paragraph."),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const textParts = messages[0].parts.filter((p: any) => p.type === "text");

      expect(textParts).toHaveLength(2);
      expect(textParts[0].text).toBe("First paragraph.");
      expect(textParts[1].text).toBe("Second paragraph.");
    });
  });

  describe("Tool Calls", () => {
    it("creates tool part from tool-input-available", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "get_weather", { location: "Seattle" }),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolPart = messages[0].parts.find(
        (p: any) => p.toolCallId === "call-1"
      ) as any;

      expect(toolPart).toBeDefined();
      expect(toolPart.type).toBe("tool-get_weather");
      expect(toolPart.toolName).toBe("get_weather");
      expect(toolPart.state).toBe("input-available");
      expect(toolPart.input).toEqual({ location: "Seattle" });
    });

    it("updates tool part with output-available", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "get_weather", { location: "Seattle" }),
        Event.toolOutputAvailable("call-1", { temperature: 72, condition: "sunny" }),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolPart = messages[0].parts.find(
        (p: any) => p.toolCallId === "call-1"
      ) as any;

      expect(toolPart.state).toBe("output-available");
      expect(toolPart.output).toEqual({ temperature: 72, condition: "sunny" });
    });

    it("handles tool output error", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "risky_tool", { action: "dangerous" }),
        Event.toolOutputError("call-1", "Permission denied"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolPart = messages[0].parts.find(
        (p: any) => p.toolCallId === "call-1"
      ) as any;

      expect(toolPart.state).toBe("output-error");
      expect(toolPart.errorText).toBe("Permission denied");
    });

    it("handles tool approval request", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "send_email", { to: "user@example.com" }),
        Event.toolApprovalRequest("call-1", "approval-123"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolPart = messages[0].parts.find(
        (p: any) => p.toolCallId === "call-1"
      ) as any;

      expect(toolPart.state).toBe("approval-requested");
      expect(toolPart.approval).toEqual({ id: "approval-123" });
    });

    it("handles tool denial", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "delete_file", { path: "/important" }),
        Event.toolApprovalRequest("call-1"),
        Event.toolOutputDenied("call-1"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolPart = messages[0].parts.find(
        (p: any) => p.toolCallId === "call-1"
      ) as any;

      expect(toolPart.state).toBe("output-denied");
      expect(toolPart.approval?.approved).toBe(false);
    });

    it("handles multiple tool calls in same message", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolInputAvailable("call-1", "get_weather", { location: "Seattle" }),
        Event.toolInputAvailable("call-2", "get_time", { timezone: "PST" }),
        Event.toolOutputAvailable("call-1", { temp: 72 }),
        Event.toolOutputAvailable("call-2", { time: "10:00 AM" }),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const toolParts = messages[0].parts.filter(
        (p: any) => p.toolCallId
      );

      expect(toolParts).toHaveLength(2);
      expect((toolParts[0] as any).toolName).toBe("get_weather");
      expect((toolParts[1] as any).toolName).toBe("get_time");
    });
  });

  describe("Step Boundaries", () => {
    it("creates step-start part for start-step event", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.startStep("step-1"),
        Event.textComplete("t1", "Step 1 result"),
        Event.finishStep("step-1"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const stepPart = messages[0].parts.find(
        (p: any) => p.type === "step-start"
      );

      expect(stepPart).toBeDefined();
    });
  });

  describe("Custom Data Events", () => {
    it("preserves custom data-app events as parts", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.dataEvent("data-app-chimera", { custom: "data" }, "app-1"),
        Event.textComplete("t1", "Response"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);
      const dataPart = messages[0].parts.find(
        (p: any) => p.type === "data-app-chimera"
      ) as any;

      expect(dataPart).toBeDefined();
      expect(dataPart.data).toEqual({ custom: "data" });
      expect(dataPart.id).toBe("app-1");
    });
  });

  describe("Edge Cases", () => {
    it("returns empty array for empty events", () => {
      const messages = hydrateFromEvents([]);
      expect(messages).toEqual([]);
    });

    it("ignores events before first agent-start", () => {
      const events = [
        Event.textComplete("orphan", "Lost text"), // No agent-start yet
        Event.agentStart("a1", "Agent"),
        Event.textComplete("t1", "Real text"),
        Event.agentFinish("a1", "Agent"),
      ];

      const messages = hydrateFromEvents(events);

      expect(messages).toHaveLength(1);
      const textParts = messages[0].parts.filter((p: any) => p.type === "text");
      expect(textParts).toHaveLength(1);
      expect(textParts[0].text).toBe("Real text");
    });

    it("warns on agent-finish without start (no crash)", () => {
      const events = [
        Event.agentFinish("orphan", "Orphan Agent"),
        Event.agentStart("a1", "Agent"),
        Event.textComplete("t1", "Hello"),
        Event.agentFinish("a1", "Agent"),
      ];

      // Should not throw
      const messages = hydrateFromEvents(events);
      expect(messages).toHaveLength(1);
    });

    it("warns on tool output for unknown toolCallId (no crash)", () => {
      const events = [
        Event.agentStart("a1", "Agent"),
        Event.toolOutputAvailable("unknown-call", { data: "orphan" }),
        Event.textComplete("t1", "Response"),
        Event.agentFinish("a1", "Agent"),
      ];

      // Should not throw
      const messages = hydrateFromEvents(events);
      expect(messages).toHaveLength(1);
    });
  });
});
