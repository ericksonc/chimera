import { useChat } from "@ai-sdk/react";
import { useRef, useEffect, useState, useMemo } from "react";
import { ReactMetrics } from "../lib/react-metrics";
import { ChimeraTransport } from "../lib/chimera-transport";
import type { ThreadMetadata } from "../stores/threadStore";
import type { ThreadProtocolEvent } from "../lib/thread-protocol";
import type { ToolUIPart, UIMessage } from "ai";

export interface UseChimeraChatOptions {
  transport: ChimeraTransport;
  currentThread: { metadata: ThreadMetadata; events: ThreadProtocolEvent[] };
  initialMessages: UIMessage[];
}

export function useChimeraChat({
  transport,
  currentThread,
  initialMessages,
}: UseChimeraChatOptions) {
  const metricsRef = useRef<ReactMetrics>(new ReactMetrics());
  const lastContentLengthRef = useRef<number>(0);

  const { messages, sendMessage, status } = useChat({
    transport,
    messages: initialMessages,
    experimental_throttle: 50,
    onFinish: () => {
      metricsRef.current.logFinal();
      // Reset for next message
      metricsRef.current = new ReactMetrics();
      lastContentLengthRef.current = 0;
    },
  });

  // Tool approval state
  const [pendingApprovals, setPendingApprovals] = useState<
    Record<string, boolean | { approved: boolean; message?: string }>
  >({});
  const [isSubmittingApprovals, setIsSubmittingApprovals] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  const handleSendMessage = (
    text: string,
    options?: { clientContext?: Record<string, unknown> }
  ) => {
    if (import.meta.env.DEV) {
      console.log(
        "[ChimeraChat] handleSendMessage called with:",
        text,
        options
      );
      console.log("[ChimeraChat] Transport:", transport);
      console.log("[ChimeraChat] Status:", status);
      console.log("[ChimeraChat] Calling sendMessage...");
    }
    sendMessage(
      { text },
      {
        body: options?.clientContext
          ? { client_context: options.clientContext }
          : undefined,
      }
    );
  };

  // Tool approval handlers
  const handleApprove = (toolCallId: string) => {
    if (import.meta.env.DEV) {
      console.log("[ChimeraChat] Approving tool:", toolCallId);
    }
    setPendingApprovals((prev) => ({
      ...prev,
      [toolCallId]: true,
    }));
  };

  const handleDeny = (toolCallId: string, message?: string) => {
    if (import.meta.env.DEV) {
      console.log("[ChimeraChat] Denying tool:", toolCallId, message);
    }
    setPendingApprovals((prev) => ({
      ...prev,
      [toolCallId]: message ? { approved: false, message } : false,
    }));
  };

  const submitApprovals = async () => {
    if (Object.keys(pendingApprovals).length === 0) return;

    if (import.meta.env.DEV) {
      console.log("[ChimeraChat] Submitting approvals:", pendingApprovals);
    }
    setIsSubmittingApprovals(true);
    setApprovalError(null);

    try {
      // Clone so transport can't mutate React state
      transport.setPendingApprovals({ ...pendingApprovals });

      // Call sendMessage - SDK will automatically process the stream!
      await sendMessage();

      // Clear approvals after successful submission
      setPendingApprovals({});
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("[ChimeraChat] Failed to submit approvals:", error);
      }
      setApprovalError(
        error instanceof Error
          ? error.message
          : "Failed to submit approvals. Please try again."
      );
    } finally {
      setIsSubmittingApprovals(false);
    }
  };

  // Memoize tools needing approval to avoid O(n) recalculation on every render
  const toolsNeedingApproval = useMemo(
    () =>
      messages
        .flatMap((m) => m.parts)
        .filter(
          (part): part is ToolUIPart =>
            part.type.startsWith("tool-") &&
            (part as ToolUIPart).state === "input-available"
        ),
    [messages]
  );

  const approveAll = () => {
    const approvals: Record<string, boolean> = {};
    toolsNeedingApproval.forEach((tool) => {
      approvals[tool.toolCallId] = true;
    });
    setPendingApprovals(approvals);
  };

  const denyAll = () => {
    const approvals: Record<string, boolean> = {};
    toolsNeedingApproval.forEach((tool) => {
      approvals[tool.toolCallId] = false;
    });
    setPendingApprovals(approvals);
  };

  const isLoading = status === "submitted" || status === "streaming";
  const hasPendingTools = toolsNeedingApproval.length > 0;

  // Track message content changes for metrics
  useEffect(() => {
    if (messages.length === 0) return;

    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role !== "assistant") return;

    const textContent = lastMessage.parts
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("");

    const currentLength = textContent.length;

    if (currentLength > lastContentLengthRef.current) {
      const deltaSize = currentLength - lastContentLengthRef.current;
      metricsRef.current.recordUpdate(deltaSize);
      lastContentLengthRef.current = currentLength;
    }
  }, [messages]);

  // Track renders
  useEffect(() => {
    metricsRef.current.recordRender();
  });

  // Debug logging (development only)
  if (import.meta.env.DEV) {
    console.log("=== CHIMERA CHAT RENDER ===");
    console.log("Status:", status);
    console.log("Thread:", currentThread.metadata.thread_id);
    console.log("Message count:", messages.length);
    if (messages.length > 0) {
      console.log("Last message parts:", messages[messages.length - 1].parts);
    }
  }

  return {
    messages,
    status,
    isLoading,
    handleSendMessage,
    // Tool approval
    pendingApprovals,
    toolsNeedingApproval,
    hasPendingTools,
    isSubmittingApprovals,
    approvalError,
    handleApprove,
    handleDeny,
    submitApprovals,
    approveAll,
    denyAll,
  };
}
