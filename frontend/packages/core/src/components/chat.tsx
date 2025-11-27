import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useRef, useEffect } from "react";
import { Message } from "./ui/message";
import { ChatInput } from "./ui/chat-input";
import { ReactMetrics } from "../lib/react-metrics";

export function Chat() {
  const metricsRef = useRef<ReactMetrics>(new ReactMetrics());
  const lastContentLengthRef = useRef<number>(0);

  const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({
      api: "http://localhost:33002/stream",
    }),
    experimental_throttle: 50,
    onFinish: () => {
      metricsRef.current.logFinal();
      // Reset for next message
      metricsRef.current = new ReactMetrics();
      lastContentLengthRef.current = 0;
    },
  });

  const handleSendMessage = (text: string) => {
    sendMessage({ text });
  };

  const isLoading = status === "submitted" || status === "streaming";

  // Track message content changes
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

  // Debug: Log detailed message info
  console.log("=== RENDER ===");
  console.log("Status:", status);
  console.log("Message count:", messages.length);
  messages.forEach((msg, i) => {
    console.log(`[${i}] ${msg.role} (${msg.id}):`, {
      partsCount: msg.parts.length,
      parts: msg.parts.map((p) => ({
        type: p.type,
        textLen: "text" in p ? p.text?.length || 0 : 0,
        state: "state" in p ? p.state : undefined,
      })),
    });
  });

  return (
    <div className="flex flex-col h-screen bg-background">
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <p>Send a message to start the conversation</p>
          </div>
        ) : (
          messages.map((message) => {
            // Render each part's text inline for streaming
            const textContent = message.parts
              .filter((part) => part.type === "text")
              .map((part) => part.text)
              .join("");

            return (
              <Message
                key={message.id}
                role={message.role}
                content={textContent}
              />
            );
          })
        )}
      </div>
      <ChatInput
        onSubmit={handleSendMessage}
        disabled={isLoading}
        placeholder={
          isLoading ? "Waiting for response..." : "Type a message..."
        }
      />
    </div>
  );
}
