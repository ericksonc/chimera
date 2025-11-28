/**
 * Tests for ChimeraTransport - SSE streaming and ThreadProtocol persistence.
 *
 * ChimeraTransport is the bridge between Vercel AI SDK and Chimera backend.
 * Key responsibilities tested:
 * 1. SSE stream processing - parsing "data: {...}" lines
 * 2. Delta accumulation - text-start/delta/end → text-complete
 * 3. Event persistence - accumulated events saved via StorageAdapter
 * 4. Tool approval flow - handling requiresApproval tools
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ChimeraTransport } from "../../packages/core/src/lib/chimera-transport";
import {
  createMockResponse,
  VSP,
  Scenarios,
} from "../helpers/sse-mock";
import type { StorageAdapter, ThreadProtocolEvent } from "../../packages/platform/src/adapters";
import type { UIMessage } from "ai";

/** Create a mock StorageAdapter */
function createMockStorageAdapter() {
  const events: ThreadProtocolEvent[] = [];
  return {
    adapter: {
      listThreads: vi.fn().mockResolvedValue([]),
      createThread: vi.fn().mockResolvedValue("test-thread-id"),
      loadThread: vi.fn().mockResolvedValue([]),
      appendThreadEvents: vi.fn().mockImplementation(async (_threadId: string, newEvents: ThreadProtocolEvent[]) => {
        events.push(...newEvents);
      }),
      listBlueprints: vi.fn().mockResolvedValue([]),
      readBlueprint: vi.fn().mockResolvedValue("{}"),
    } as StorageAdapter,
    events,
    getPersistedEvents: () => events,
  };
}

/** Create a minimal UIMessage for testing */
function createUserMessage(content: string): UIMessage {
  return {
    id: `msg-${Date.now()}`,
    role: "user",
    parts: [{ type: "text", text: content }],
    createdAt: new Date(),
  };
}

/** Collect all chunks from a ReadableStream */
async function collectStream<T>(stream: ReadableStream<T>): Promise<T[]> {
  const reader = stream.getReader();
  const chunks: T[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  return chunks;
}

describe("ChimeraTransport", () => {
  let mockStorage: ReturnType<typeof createMockStorageAdapter>;
  let transport: ChimeraTransport;
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    mockStorage = createMockStorageAdapter();
    transport = new ChimeraTransport({
      threadId: "test-thread-123",
      backendUrl: "http://localhost:8765",
      storageAdapter: mockStorage.adapter,
    });
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  describe("SSE Stream Processing", () => {
    it("processes simple text response", async () => {
      // Arrange: Mock backend returns a simple text response
      const events = Scenarios.simpleTextResponse(
        "agent-1",
        "Test Agent",
        "text-1",
        "Hello, world!"
      );
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act: Send a message and collect the stream
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Hi")],
      });
      const chunks = await collectStream(stream);

      // Assert: Stream contains expected chunks
      expect(chunks.length).toBeGreaterThan(0);

      // Find the text-delta chunk
      const textDelta = chunks.find((c: any) => c.type === "text-delta");
      expect(textDelta).toBeDefined();
      expect((textDelta as any)?.delta).toBe("Hello, world!");
    });

    it("accumulates text deltas into text-complete event", async () => {
      // Arrange: Text streamed in multiple chunks
      const events = [
        VSP.agentStart("agent-1", "Test"),
        VSP.textStart("text-1"),
        VSP.textDelta("text-1", "Hello"),
        VSP.textDelta("text-1", ", "),
        VSP.textDelta("text-1", "world!"),
        VSP.textEnd("text-1"),
        VSP.agentFinish("agent-1", "Test"),
      ];
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Hi")],
      });
      await collectStream(stream);

      // Assert: text-complete event persisted with full content
      const persisted = mockStorage.getPersistedEvents();
      const textComplete = persisted.find((e) => e.type === "text-complete");

      expect(textComplete).toBeDefined();
      expect(textComplete?.content).toBe("Hello, world!");
    });

    it("handles agent boundary events", async () => {
      // Arrange
      const events = [
        VSP.agentStart("jarvis", "Jarvis"),
        VSP.textStart("t1"),
        VSP.textDelta("t1", "I am Jarvis"),
        VSP.textEnd("t1"),
        VSP.agentFinish("jarvis", "Jarvis"),
      ];
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Who are you?")],
      });
      const chunks = await collectStream(stream);

      // Assert: Agent start/finish events pass through
      const agentStart = chunks.find((c: any) => c.type === "data-agent-start");
      const agentFinish = chunks.find(
        (c: any) => c.type === "data-agent-finish"
      );

      expect(agentStart).toBeDefined();
      expect((agentStart as any)?.data.agentId).toBe("jarvis");
      expect(agentFinish).toBeDefined();
    });
  });

  describe("Tool Call Flow", () => {
    it("processes tool call without approval", async () => {
      // Arrange: Tool call that auto-executes
      const events = Scenarios.autoApprovedToolCall(
        "agent-1",
        "Test",
        "call-1",
        "get_weather",
        { location: "Seattle" },
        { temperature: 72, condition: "sunny" }
      );
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("What's the weather?")],
      });
      const chunks = await collectStream(stream);

      // Assert: Tool input and output events pass through
      const toolInput = chunks.find(
        (c: any) => c.type === "tool-input-available"
      );
      const toolOutput = chunks.find(
        (c: any) => c.type === "tool-output-available"
      );

      expect(toolInput).toBeDefined();
      expect((toolInput as any)?.toolName).toBe("get_weather");
      expect(toolOutput).toBeDefined();
    });

    it("handles tool approval request", async () => {
      // Arrange: Tool that requires approval
      const events = Scenarios.toolCallRequiringApproval(
        "agent-1",
        "Test",
        "call-1",
        "send_email",
        { to: "user@example.com", subject: "Hello" }
      );
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Send an email")],
      });
      const chunks = await collectStream(stream);

      // Assert: Approval request passes through for UI handling
      const approvalRequest = chunks.find(
        (c: any) => c.type === "tool-approval-request"
      );

      expect(approvalRequest).toBeDefined();
      expect((approvalRequest as any)?.toolCallId).toBe("call-1");
    });

    it("sends pending approvals with next message", async () => {
      // Arrange: First call triggers approval request
      const initialEvents = Scenarios.toolCallRequiringApproval(
        "agent-1",
        "Test",
        "call-1",
        "delete_file",
        { path: "/tmp/test.txt" }
      );
      fetchSpy.mockResolvedValue(createMockResponse(initialEvents));

      // First request
      const stream1 = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Delete the file")],
      });
      await collectStream(stream1);

      // Set approval
      transport.setPendingApprovals({ "call-1": true });

      // Mock response for approval continuation
      const continuationEvents = [
        VSP.toolOutputAvailable("call-1", { deleted: true }),
        VSP.agentFinish("agent-1", "Test"),
      ];
      fetchSpy.mockResolvedValue(createMockResponse(continuationEvents));

      // Act: Send continuation
      const stream2 = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("")], // Empty message for continuation
      });
      await collectStream(stream2);

      // Assert: Request body should include deferred_tools
      expect(fetchSpy).toHaveBeenCalledTimes(2);
      const lastCall = fetchSpy.mock.calls[1];
      const requestBody = JSON.parse(lastCall[1]?.body as string);

      expect(requestBody.user_input.kind).toBe("deferred_tools");
      expect(requestBody.user_input.approvals["call-1"]).toBe(true);
    });
  });

  describe("Event Persistence", () => {
    it("persists accumulated events to storage", async () => {
      // Arrange
      const events = Scenarios.simpleTextResponse(
        "agent-1",
        "Test",
        "text-1",
        "Hello!"
      );
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Hi")],
      });
      await collectStream(stream);

      // Assert: appendThreadEvents was called
      expect(mockStorage.adapter.appendThreadEvents).toHaveBeenCalledWith(
        "test-thread-123",
        expect.any(Array)
      );

      // Check persisted events include key types
      const persisted = mockStorage.getPersistedEvents();
      const eventTypes = persisted.map((e) => e.type);

      expect(eventTypes).toContain("data-agent-start");
      expect(eventTypes).toContain("text-complete");
      expect(eventTypes).toContain("data-agent-finish");
    });

    it("adds timestamps to persisted events", async () => {
      // Arrange
      const events = [
        VSP.agentStart("agent-1", "Test"),
        VSP.textStart("t1"),
        VSP.textDelta("t1", "Hello"),
        VSP.textEnd("t1"),
        VSP.agentFinish("agent-1", "Test"),
      ];
      fetchSpy.mockResolvedValue(createMockResponse(events));

      // Act
      const stream = await transport.sendMessages({
        trigger: "submit-message",
        chatId: "chat-1",
        messages: [createUserMessage("Hi")],
      });
      await collectStream(stream);

      // Assert: All persisted events have timestamps
      const persisted = mockStorage.getPersistedEvents();
      for (const event of persisted) {
        expect(event.timestamp).toBeDefined();
        expect(typeof event.timestamp).toBe("string");
      }
    });
  });

  describe("Error Handling", () => {
    it("throws on non-OK response", async () => {
      // Arrange
      fetchSpy.mockResolvedValue(
        new Response("Not Found", { status: 404, statusText: "Not Found" })
      );

      // Act & Assert
      await expect(
        transport.sendMessages({
          trigger: "submit-message",
          chatId: "chat-1",
          messages: [createUserMessage("Hi")],
        })
      ).rejects.toThrow("Chimera backend error: 404 Not Found");
    });

    it("throws on null response body", async () => {
      // Arrange
      const response = new Response(null, { status: 200 });
      fetchSpy.mockResolvedValue(response);

      // Act & Assert
      await expect(
        transport.sendMessages({
          trigger: "submit-message",
          chatId: "chat-1",
          messages: [createUserMessage("Hi")],
        })
      ).rejects.toThrow("Response body is null");
    });
  });
});
