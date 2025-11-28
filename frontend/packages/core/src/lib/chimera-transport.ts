import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import type { StorageAdapter } from "@chimera/platform";
import type { ThreadProtocolEvent } from "./thread-protocol";
import { addTimestamp } from "./thread-protocol";

/**
 * VSP (Vercel Streaming Protocol) event from SSE stream.
 * These are dynamic events with a `type` field that determines structure.
 * Using Record<string, unknown> with type field for basic type safety.
 */
type VSPEvent = {
  type: string;
  [key: string]: unknown;
};

/**
 * ChimeraTransport - Custom transport for Chimera backend
 *
 * Bridges Vercel AI SDK v6 <-> Chimera ThreadProtocol v0.0.7:
 * - Converts SDK messages to Chimera request format
 * - Streams VSP v6 events from Chimera
 * - Accumulates ThreadProtocol events for persistence
 * - Converts VSP back to SDK format
 */

/**
 * ThreadProtocol v0.0.7 - "Condensed VSP v6"
 *
 * VSP events pass through directly to ThreadProtocol, except for:
 * 1. Delta condensation (streaming deltas -> complete events)
 *    - text-start/delta-deltas/end -> text-complete
 *    - reasoning-start/delta-deltas/end -> reasoning-complete
 *    - tool-input-start/delta-deltas/available -> tool-input-available (keep final)
 * 2. Event accumulation during streaming
 *
 * All other events pass through unchanged!
 */

/**
 * User input formats (discriminated union)
 */
type UserInputMessage = {
  kind: "message";
  content: string;
  client_context?: Record<string, unknown>;
};

type UserInputDeferredTools = {
  kind: "deferred_tools";
  approvals: Record<
    string,
    boolean | { approved: boolean; message?: string; override_args?: unknown }
  >;
  calls: Record<string, unknown>;
  client_context?: Record<string, unknown>;
};

interface ChimeraTransportOptions {
  /** Thread ID for this conversation */
  threadId: string;
  /** Backend URL */
  backendUrl: string;
  /** Storage adapter for persisting events */
  storageAdapter: StorageAdapter;
  /** Callback when new complete events are accumulated */
  onEventsAccumulated?: (events: ThreadProtocolEvent[]) => void;
}

interface DeltaAccumulator {
  id: string;
  type: "text" | "tool-call" | "reasoning";
  content: string;
  toolName?: string;
  toolCallId?: string;
  args?: string;
}

export class ChimeraTransport implements ChatTransport<UIMessage> {
  private threadId: string;
  private backendUrl: string;
  private storageAdapter: StorageAdapter;
  private onEventsAccumulated?: (events: ThreadProtocolEvent[]) => void;
  private threadProtocol: ThreadProtocolEvent[] = [];
  private accumulators = new Map<string, DeltaAccumulator>();
  private pendingEvents: ThreadProtocolEvent[] = [];
  private currentAgentId?: string; // Track current agent for tool calls
  private pendingToolApprovals?: {
    approvals: Record<
      string,
      boolean | { approved: boolean; message?: string; override_args?: unknown }
    >;
    calls?: Record<string, unknown>;
  }; // Track pending approvals for next sendMessage

  constructor(options: ChimeraTransportOptions) {
    this.threadId = options.threadId;
    this.backendUrl = options.backendUrl;
    this.storageAdapter = options.storageAdapter;
    this.onEventsAccumulated = options.onEventsAccumulated;
  }

  async sendMessages(options: {
    trigger: "submit-message" | "regenerate-message";
    chatId: string;
    messageId?: string;
    messages: UIMessage[];
    abortSignal?: AbortSignal;
    headers?: Record<string, string> | Headers;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- SDK interface
    body?: Record<string, any>;
    metadata?: unknown;
  }): Promise<ReadableStream<UIMessageChunk>> {
    console.log("[ChimeraTransport] sendMessages called!", options);

    // Check if we have pending tool approvals
    let userInput: UserInputMessage | UserInputDeferredTools;

    // Extract client_context from body if present
    const clientContext = options.body?.client_context;

    if (this.pendingToolApprovals) {
      // Use deferred_tools input
      console.log(
        "[ChimeraTransport] Using pending tool approvals:",
        this.pendingToolApprovals
      );
      userInput = {
        kind: "deferred_tools",
        approvals: this.pendingToolApprovals.approvals,
        calls: this.pendingToolApprovals.calls || {},
        ...(clientContext ? { client_context: clientContext } : {}),
      };
      // Clear pending approvals
      this.pendingToolApprovals = undefined;
    } else {
      // Extract user input from last message
      const lastMessage = options.messages[options.messages.length - 1];
      userInput = {
        ...this.extractUserInput(lastMessage),
        ...(clientContext ? { client_context: clientContext } : {}),
      };
    }

    // Build Chimera request
    const request = {
      thread_protocol: this.threadProtocol,
      user_input: userInput,
    };

    console.log("[ChimeraTransport] Sending request:", {
      threadId: this.threadId,
      historyEventCount: this.threadProtocol.length,
      userInput,
    });
    console.log(
      "[ChimeraTransport] First 2 thread_protocol events:",
      JSON.stringify(this.threadProtocol.slice(0, 2), null, 2)
    );

    // Convert Headers object to plain object if needed
    const headersObj =
      options.headers instanceof Headers
        ? Object.fromEntries(options.headers.entries())
        : options.headers;

    // Make request to Chimera backend
    const response = await fetch(`${this.backendUrl}/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...headersObj,
      },
      body: JSON.stringify(request),
      signal: options.abortSignal,
    });

    if (!response.ok) {
      throw new Error(
        `Chimera backend error: ${response.status} ${response.statusText}`
      );
    }

    if (!response.body) {
      throw new Error("Response body is null");
    }

    // Process SSE stream and convert to UIMessageChunk
    return this.processVSPStream(response.body);
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    // Not implementing reconnect for now
    return null;
  }

  /**
   * Set pending tool approvals/denials for next sendMessage call
   * This integrates with the SDK's flow - after calling this, call sendMessage()
   */
  setPendingApprovals(
    approvals: Record<
      string,
      boolean | { approved: boolean; message?: string; override_args?: unknown }
    >,
    calls?: Record<string, unknown>
  ): void {
    this.pendingToolApprovals = {
      approvals,
      calls: calls || {},
    };
    console.log("[ChimeraTransport] Set pending approvals:", {
      approvalCount: Object.keys(approvals).length,
      callCount: Object.keys(calls || {}).length,
    });
  }

  /**
   * Extract user input from UIMessage and format as UserInputMessage
   */
  private extractUserInput(message: UIMessage): UserInputMessage {
    if (message.role !== "user") {
      throw new Error("Last message must be from user");
    }

    // Extract text from parts
    const content = message.parts
      .filter((part) => part.type === "text")
      .map((part) => ("text" in part ? part.text : ""))
      .join("");

    return {
      kind: "message",
      content,
    };
  }

  /**
   * Process VSP SSE stream from Chimera backend
   */
  private processVSPStream(
    body: ReadableStream<Uint8Array>
  ): ReadableStream<UIMessageChunk> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<UIMessageChunk>({
      start: () => {
        this.pendingEvents = [];
        this.accumulators.clear();
      },
      pull: async (controller) => {
        try {
          const { done, value } = await reader.read();

          if (done) {
            console.log("[ChimeraTransport] Stream done, finalizing...");
            // Finalize any pending accumulators
            this.finalizeAllAccumulators();

            // Persist accumulated events
            await this.persistEvents();

            controller.close();
            return;
          }

          // Decode chunk and add to buffer
          const decoded = decoder.decode(value, { stream: true });
          console.log(
            "[ChimeraTransport] Received chunk, bytes:",
            decoded.length
          );
          buffer += decoded;

          // Process complete SSE events
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.trim() || line.startsWith(":")) continue;

            if (line.startsWith("data: ")) {
              const data = line.slice(6);

              if (data === "[DONE]") {
                continue;
              }

              try {
                const event = JSON.parse(data);

                // Debug: log all events to see full stream
                console.log(
                  "[ChimeraTransport] Raw VSP event:",
                  event.type,
                  event.toolName || ""
                );

                // Handle VSP event
                const chunk = this.handleVSPEvent(event);
                if (chunk) {
                  controller.enqueue(chunk);
                }
              } catch (e) {
                console.warn("[ChimeraTransport] Failed to parse event:", e);
                // CLI pattern: log but continue streaming
              }
            }
          }
        } catch (error) {
          console.error("[ChimeraTransport] Stream error:", error);
          controller.error(error);
        }
      },
    });
  }

  /**
   * Handle a single VSP event
   * Returns UIMessageChunk to send to Vercel SDK, or null if event is internal-only
   */
  private handleVSPEvent(event: VSPEvent): UIMessageChunk | null {
    const eventType = event.type;

    // Debug: log ALL non-delta events (including turn boundaries)
    if (!eventType.includes("-delta")) {
      console.log("[ChimeraTransport] VSP event:", eventType);
    }

    // Accumulate deltas for ThreadProtocol
    if (eventType === "text-delta") {
      this.handleTextDelta(event);
      // Pass through to SDK
      return event as UIMessageChunk;
    } else if (eventType === "text-start") {
      this.startTextAccumulator(event);
      return event as UIMessageChunk;
    } else if (eventType === "text-end") {
      this.finalizeTextAccumulator(event);
      return event as UIMessageChunk;
    } else if (eventType === "tool-input-delta") {
      this.handleToolInputDelta(event);
      return event as UIMessageChunk;
    } else if (eventType === "tool-input-start") {
      this.startToolCallAccumulator(event);
      return event as UIMessageChunk;
    } else if (eventType === "tool-input-available") {
      this.finalizeToolCallAccumulator(event);
      return event as UIMessageChunk;
    } else if (eventType === "tool-output-start") {
      return event as UIMessageChunk;
    } else if (eventType === "tool-output-delta") {
      return event as UIMessageChunk;
    } else if (eventType === "reasoning-delta") {
      this.handleReasoningDelta(event);
      return event as UIMessageChunk;
    } else if (eventType === "reasoning-start") {
      this.startReasoningAccumulator(event);
      return event as UIMessageChunk;
    } else if (eventType === "reasoning-end") {
      this.finalizeReasoningAccumulator(event);
      return event as UIMessageChunk;
    }

    // Agent boundaries (v0.0.7: custom data-* events)
    if (eventType === "data-agent-start" || eventType === "data-agent-finish") {
      // Track current agent ID for context
      if (eventType === "data-agent-start") {
        const data = event.data as { agentId?: string } | undefined;
        this.currentAgentId = data?.agentId;
      }

      // Store event for ThreadProtocol
      this.pendingEvents.push(addTimestamp(event));
      // Pass through to SDK for message grouping
      return event as UIMessageChunk;
    }

    // User message - pass through VSP format directly!
    if (eventType === "user-message") {
      this.pendingEvents.push(addTimestamp(event));
      // Pass through to SDK to keep stream processing
      return event as UIMessageChunk;
    }

    // Tool events (v6) - pass through VSP format directly!
    if (
      eventType === "tool-output-available" ||
      eventType === "tool-approval-request" ||
      eventType === "tool-output-denied" ||
      eventType === "tool-input-error" ||
      eventType === "tool-output-error"
    ) {
      this.pendingEvents.push(addTimestamp(event));
      // Pass through to SDK for UI rendering
      return event as UIMessageChunk;
    }

    // Usage telemetry - pass through VSP format directly!
    if (eventType === "data-sys-usage") {
      this.pendingEvents.push(addTimestamp(event));
      return null;
    }

    // Step boundaries - pass through VSP format directly!
    if (eventType === "start-step" || eventType === "finish-step") {
      this.pendingEvents.push(addTimestamp(event));
      return null;
    }

    // Message boundaries - track for message identity!
    if (
      eventType === "start" ||
      eventType === "finish" ||
      eventType === "abort"
    ) {
      // Note: These are NOT saved to JSONL (we use data-agent-start/finish instead)
      // but we keep them in pendingEvents during streaming for debugging
      // Pass through to SDK for message grouping
      return event as UIMessageChunk;
    }

    // Message metadata updates (v6)
    if (eventType === "message-metadata") {
      // Pass through to SDK but don't persist to JSONL
      return event as UIMessageChunk;
    }

    // Error events
    if (eventType === "error") {
      this.pendingEvents.push(addTimestamp(event));
      return null;
    }

    // Custom Chimera events (data-app-*)
    if (eventType.startsWith("data-app-")) {
      this.pendingEvents.push(addTimestamp(event));
      // Don't pass to SDK
      return null;
    }

    // Pass through any other VSP events
    return event as UIMessageChunk;
  }

  // Text accumulation
  private startTextAccumulator(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    this.accumulators.set(id, {
      id,
      type: "text",
      content: "",
    });
  }

  private handleTextDelta(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "text") {
      acc.content += (event.delta as string) || "";
    }
  }

  private finalizeTextAccumulator(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "text") {
      // Create text-complete event for ThreadProtocol v0.0.7
      this.pendingEvents.push(
        addTimestamp({
          type: "text-complete",
          id: acc.id, // Include VSP text block ID
          content: acc.content, // v0.0.7: field is "content"
          providerMetadata: event.providerMetadata,
        })
      );
      this.accumulators.delete(id);
    }
  }

  // Tool call accumulation
  private startToolCallAccumulator(event: VSPEvent) {
    const id = event.toolCallId as string;
    this.accumulators.set(id, {
      id,
      type: "tool-call",
      content: "",
      toolName: event.toolName as string,
      toolCallId: id,
      args: "",
    });
  }

  private handleToolInputDelta(event: VSPEvent) {
    const id = event.toolCallId as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "tool-call") {
      acc.args += (event.inputTextDelta as string) || "";
    }
  }

  private finalizeToolCallAccumulator(event: VSPEvent) {
    const id = event.toolCallId as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "tool-call") {
      // Parse args JSON string to object (v0.0.6 uses objects!)
      let inputObj: unknown = {};
      try {
        inputObj = JSON.parse(acc.args || "{}");
      } catch (e) {
        console.warn("[ChimeraTransport] Failed to parse tool args:", e);
        inputObj = {};
      }

      // Use VSP format: tool-input-available with input field
      const toolCallEvent: ThreadProtocolEvent = {
        type: "tool-input-available",
        toolCallId: acc.toolCallId!,
        toolName: acc.toolName || (event.toolName as string),
        input: inputObj, // Object, not string!
      };

      // Add agentId if we're tracking one
      if (this.currentAgentId) {
        toolCallEvent.agentId = this.currentAgentId;
      }

      const timestampedEvent = addTimestamp(toolCallEvent);
      this.pendingEvents.push(timestampedEvent);

      // CRITICAL: Persist tool call immediately!
      // Backend needs this in JSONL before tool execution/approval
      this.persistToolCallImmediate(timestampedEvent).catch((err) => {
        console.error("[ChimeraTransport] Failed to persist tool call:", err);
      });

      this.accumulators.delete(id);
    }
  }

  // Reasoning accumulation (v6: renamed from "thinking")
  private startReasoningAccumulator(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    this.accumulators.set(id, {
      id,
      type: "reasoning",
      content: "",
    });
  }

  private handleReasoningDelta(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "reasoning") {
      acc.content += (event.delta as string) || "";
    }
  }

  private finalizeReasoningAccumulator(event: VSPEvent) {
    const id = (event.id || event.messageId) as string;
    const acc = this.accumulators.get(id);
    if (acc && acc.type === "reasoning") {
      // Create reasoning-complete event for ThreadProtocol v0.0.7
      this.pendingEvents.push(
        addTimestamp({
          type: "reasoning-complete",
          id: acc.id, // Include VSP reasoning block ID
          content: acc.content, // v0.0.7: field is "content"
          providerMetadata: event.providerMetadata,
        })
      );
      this.accumulators.delete(id);
    }
  }

  // Finalize all accumulators at end of stream
  private finalizeAllAccumulators() {
    for (const [, acc] of this.accumulators.entries()) {
      if (acc.type === "text" && acc.content) {
        this.pendingEvents.push(
          addTimestamp({
            type: "text-complete",
            id: acc.id, // Include VSP text block ID
            content: acc.content, // v0.0.7: field is "content"
          })
        );
      } else if (acc.type === "tool-call") {
        // Parse args JSON string to object (v0.0.7 uses objects!)
        let inputObj: unknown = {};
        try {
          inputObj = JSON.parse(acc.args || "{}");
        } catch (e) {
          console.warn("[ChimeraTransport] Failed to parse tool args:", e);
          inputObj = {};
        }

        // Use VSP format: tool-input-available with input field
        const toolCallEvent: ThreadProtocolEvent = {
          type: "tool-input-available",
          toolCallId: acc.toolCallId!,
          toolName: acc.toolName!,
          input: inputObj, // Object, not string!
        };

        // Add agentId if we're tracking one
        if (this.currentAgentId) {
          toolCallEvent.agentId = this.currentAgentId;
        }

        const timestampedEvent = addTimestamp(toolCallEvent);
        this.pendingEvents.push(timestampedEvent);

        // CRITICAL: Persist tool call immediately!
        // Even at stream end, persist tool calls right away
        this.persistToolCallImmediate(timestampedEvent).catch((err) => {
          console.error("[ChimeraTransport] Failed to persist tool call:", err);
        });
      } else if (acc.type === "reasoning" && acc.content) {
        this.pendingEvents.push(
          addTimestamp({
            type: "reasoning-complete",
            id: acc.id, // Include VSP reasoning block ID
            content: acc.content, // v0.0.7: field is "content"
          })
        );
      }
    }
    this.accumulators.clear();
  }

  /**
   * Persist accumulated events to storage via adapter
   */
  private async persistEvents() {
    if (this.pendingEvents.length === 0) {
      console.log("[ChimeraTransport] No events to persist");
      return;
    }

    console.log(
      `[ChimeraTransport] Persisting ${this.pendingEvents.length} events to thread ${this.threadId}`
    );
    console.log(
      "[ChimeraTransport] Event types:",
      this.pendingEvents.map((e) => e.type).join(", ")
    );

    try {
      // Append to storage via adapter
      await this.storageAdapter.appendThreadEvents(
        this.threadId,
        this.pendingEvents
      );

      // Update in-memory thread protocol
      this.threadProtocol.push(...this.pendingEvents);

      // Notify callback
      if (this.onEventsAccumulated) {
        this.onEventsAccumulated(this.pendingEvents);
      }

      // Clear pending
      this.pendingEvents = [];
    } catch (error) {
      console.error("[ChimeraTransport] Failed to persist events:", error);
      throw error;
    }
  }

  /**
   * Immediately persist a tool-input-available event to storage
   *
   * CRITICAL: Tool calls must be persisted immediately because the backend
   * reads storage to reconstruct thread history when resuming after tool approval.
   * If tool-input-available is only in pendingEvents[], the backend can't find
   * the tool call and throws: "Tool call results were provided, but the message
   * history does not contain a `ModelResponse`"
   *
   * Fire-and-forget async - doesn't block stream processing.
   * Fallback: If persist fails, event stays in pendingEvents for stream-end persist.
   */
  private async persistToolCallImmediate(
    event: ThreadProtocolEvent
  ): Promise<void> {
    try {
      console.log(
        `[ChimeraTransport] Immediately persisting tool call: ${event.toolName as string}`
      );

      await this.storageAdapter.appendThreadEvents(this.threadId, [event]);

      // Update in-memory protocol
      this.threadProtocol.push(event);

      // Remove from pending (already persisted)
      const index = this.pendingEvents.indexOf(event);
      if (index > -1) {
        this.pendingEvents.splice(index, 1);
      }

      console.log(
        `[ChimeraTransport] ✓ Tool call persisted: ${event.toolCallId as string}`
      );
    } catch (error) {
      console.error("[ChimeraTransport] Immediate persist failed:", error);
      // Keep in pendingEvents as fallback - will be persisted at stream end
    }
  }

  /**
   * Load existing thread history
   */
  async loadHistory(): Promise<void> {
    try {
      const events = await this.storageAdapter.loadThread(this.threadId);
      console.log(
        `[ChimeraTransport] Loaded ${events.length} events from thread ${this.threadId}`
      );
      console.log("[ChimeraTransport] First event type:", typeof events[0]);
      console.log(
        "[ChimeraTransport] First event:",
        JSON.stringify(events[0], null, 2)
      );
      this.threadProtocol = events;
    } catch {
      console.warn(
        `[ChimeraTransport] No existing thread found (${this.threadId}), starting fresh`
      );
      this.threadProtocol = [];
    }
  }

  /**
   * Get current thread protocol events
   */
  getThreadProtocol(): ThreadProtocolEvent[] {
    return this.threadProtocol;
  }
}
