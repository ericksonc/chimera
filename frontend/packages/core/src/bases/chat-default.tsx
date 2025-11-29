import { useEffect, useState, useRef, useCallback } from "react";

import { useBlueprint } from "../providers/BlueprintProvider";
import { useAdapters } from "../providers/AdapterProvider";
import { useThreadStore } from "../stores/threadStore";
import { ChimeraTransport } from "../lib/chimera-transport";
import { hydrateFromEvents } from "../lib/jsonl-hydrator";
import { useChimeraChat } from "../hooks/useChimeraChat";
import { cn } from "../lib/utils";
import type { UIMessage } from "ai";

// ============================================================================
// Title Generation Utility
// ============================================================================

interface UtilResponse {
  result: string;
  model_used: string;
}

async function generateTitleFromPrompt(
  backendUrl: string,
  userPrompt: string
): Promise<string> {
  const response = await fetch(`${backendUrl}/util`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task: "generate_title",
      input: { user_prompt: userPrompt },
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to generate title: ${response.statusText}`);
  }

  const data: UtilResponse = await response.json();
  return data.result;
}

// AI Elements
import {
  Artifact,
  ArtifactContent,
  ArtifactDescription,
  ArtifactHeader,
  ArtifactTitle,
} from "../components/ai-elements/artifact";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "../components/ai-elements/conversation";
import { Message, MessageContent } from "../components/ai-elements/message";
import { Response } from "../components/ai-elements/response";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "../components/ai-elements/reasoning";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "../components/ai-elements/tool";
import {
  Confirmation,
  ConfirmationActions,
  ConfirmationAction,
  ConfirmationTitle,
  ConfirmationRequest,
} from "../components/ai-elements/confirmation";
import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputActionAddAttachments,
} from "../components/ai-elements/prompt-input";

// UI Components
import { Button } from "../components/ui/button";
import { Alert, AlertDescription } from "../components/ui/alert";

// Icons
import { MessageSquarePlus, Search, Sparkles } from "lucide-react";

import type { ToolUIPart } from "ai";

// ============================================================================
// Typing Headline Component
// ============================================================================

const headlines = [
  "Ready when you are.",
  "Let's dive in.",
  "What's on your mind?",
  "How can I help today?",
  "Let's build something.",
];

function TypingHeadline() {
  const [displayed, setDisplayed] = useState("");
  const [showCursor, setShowCursor] = useState(true);
  const [text] = useState(
    () => headlines[Math.floor(Math.random() * headlines.length)]
  );

  useEffect(() => {
    let idx = 0;
    const interval = setInterval(() => {
      if (idx < text.length) {
        setDisplayed(text.slice(0, idx + 1));
        idx++;
      } else {
        clearInterval(interval);
      }
    }, 50);
    return () => clearInterval(interval);
  }, [text]);

  useEffect(() => {
    const interval = setInterval(() => setShowCursor((c) => !c), 530);
    return () => clearInterval(interval);
  }, []);

  return (
    <h1 className="text-3xl font-light tracking-tight text-foreground mb-8 text-center">
      {displayed}
      <span
        className={cn(
          "ml-0.5 inline-block w-[2px] h-8 bg-foreground/70 align-middle transition-opacity",
          showCursor ? "opacity-100" : "opacity-0"
        )}
      />
    </h1>
  );
}

// ============================================================================
// Sidebar Component
// ============================================================================

interface SidebarProps {
  onNewChat: () => void;
}

function Sidebar({ onNewChat }: SidebarProps) {
  const { currentBlueprintId: _currentBlueprintId } = useBlueprint();
  const { threads, currentThread, loadThreads, loadThread } = useThreadStore();

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  // Filter threads by current blueprint
  // TODO: Add blueprint filtering once we have blueprint ID in thread metadata
  const filteredThreads = threads;

  return (
    <aside className="w-60 shrink-0 flex flex-col border-r bg-card/50">
      {/* Top Actions */}
      <div className="p-3 space-y-1">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors"
        >
          <MessageSquarePlus className="size-4" />
          New chat
        </button>
        <button
          type="button"
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors"
        >
          <Search className="size-4" />
          Search chats
        </button>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <div>
          <h3 className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Conversations
          </h3>
          <div className="space-y-0.5">
            {filteredThreads.length === 0 ? (
              <p className="px-3 py-2 text-sm text-muted-foreground">
                No conversations yet
              </p>
            ) : (
              filteredThreads.map((thread) => {
                const isActive =
                  currentThread?.metadata.thread_id === thread.thread_id;
                return (
                  <button
                    type="button"
                    key={thread.thread_id}
                    onClick={() => loadThread(thread.thread_id)}
                    className={cn(
                      "w-full text-left px-3 py-2 text-sm rounded-md transition-colors truncate",
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-foreground/80 hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    {thread.title || "Untitled"}
                  </button>
                );
              })
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

// ============================================================================
// Chat Content Component (when thread is selected)
// ============================================================================

interface ReasoningPart {
  type: "reasoning";
  text?: string;
  details?: string;
}

interface ChatContentProps {
  transport: ChimeraTransport;
  initialMessages: UIMessage[];
  pendingMessage?: string | null;
  onPendingMessageSent?: () => void;
}

function ChatContent({
  transport,
  initialMessages,
  pendingMessage,
  onPendingMessageSent,
}: ChatContentProps) {
  const { currentThread } = useThreadStore();
  const pendingMessageSentRef = useRef(false);

  const {
    messages,
    isLoading,
    handleSendMessage,
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
  } = useChimeraChat({
    transport,
    currentThread: currentThread!,
    initialMessages,
  });

  // Send pending message once (from new chat flow)
  useEffect(() => {
    if (pendingMessage && !pendingMessageSentRef.current) {
      pendingMessageSentRef.current = true;
      console.log("[ChatContent] Sending pending message:", pendingMessage);
      handleSendMessage(pendingMessage);
      onPendingMessageSent?.();
    }
  }, [pendingMessage, handleSendMessage, onPendingMessageSent]);

  return (
    <>
      <Conversation className="flex-1">
        <ConversationContent className="max-w-3xl mx-auto">
          {messages.map((message) => (
            <Message key={message.id} from={message.role}>
              <MessageContent>
                {message.parts.map((part, index) => {
                  if (part.type === "text") {
                    return <Response key={index}>{part.text}</Response>;
                  }

                  if (part.type.startsWith("tool-")) {
                    const toolPart = part as ToolUIPart;
                    const toolName = toolPart.type.replace("tool-", "");
                    const isAwaitingApproval =
                      toolPart.state === "input-available";

                    return (
                      <Tool key={toolPart.toolCallId}>
                        <ToolHeader
                          title={toolName}
                          type={toolPart.type}
                          state={
                            isAwaitingApproval
                              ? "approval-requested"
                              : toolPart.state
                          }
                        />
                        <ToolContent>
                          <ToolInput input={toolPart.input} />

                          {isAwaitingApproval && (
                            <Confirmation
                              approval={{ id: toolPart.toolCallId }}
                              state="approval-requested"
                            >
                              <ConfirmationTitle>
                                <ConfirmationRequest>
                                  Execute <strong>{toolName}</strong>?
                                </ConfirmationRequest>
                              </ConfirmationTitle>
                              <ConfirmationActions>
                                <ConfirmationAction
                                  onClick={() =>
                                    handleDeny(toolPart.toolCallId)
                                  }
                                  variant="outline"
                                  disabled={isSubmittingApprovals}
                                >
                                  Deny
                                </ConfirmationAction>
                                <ConfirmationAction
                                  onClick={() =>
                                    handleApprove(toolPart.toolCallId)
                                  }
                                  variant="default"
                                  disabled={isSubmittingApprovals}
                                >
                                  Approve
                                </ConfirmationAction>
                              </ConfirmationActions>
                            </Confirmation>
                          )}

                          {toolPart.state === "output-available" && (
                            <ToolOutput
                              output={toolPart.output}
                              errorText={toolPart.errorText}
                            />
                          )}
                          {toolPart.state === "output-error" && (
                            <ToolOutput
                              output={undefined}
                              errorText={toolPart.errorText}
                            />
                          )}
                        </ToolContent>
                      </Tool>
                    );
                  }

                  if (part.type === "reasoning") {
                    const isLastMessage =
                      message.id === messages[messages.length - 1].id;
                    const isStreaming = isLoading && isLastMessage;

                    return (
                      <Reasoning key={index} isStreaming={isStreaming}>
                        <ReasoningTrigger />
                        <ReasoningContent>
                          {(part as ReasoningPart).text ||
                            (part as ReasoningPart).details ||
                            ""}
                        </ReasoningContent>
                      </Reasoning>
                    );
                  }

                  return null;
                })}
              </MessageContent>
            </Message>
          ))}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Batch Approval UI */}
      {hasPendingTools && (
        <div className="border-t bg-muted/50 px-4 py-3">
          <div className="flex flex-col gap-3 max-w-3xl mx-auto">
            {approvalError && (
              <Alert variant="destructive">
                <AlertDescription>{approvalError}</AlertDescription>
              </Alert>
            )}
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium">
                {toolsNeedingApproval.length} tool
                {toolsNeedingApproval.length !== 1 ? "s" : ""} awaiting approval
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={denyAll}
                  disabled={isSubmittingApprovals}
                >
                  Deny All
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={approveAll}
                  disabled={isSubmittingApprovals}
                >
                  Approve All
                </Button>
                {Object.keys(pendingApprovals).length > 0 && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={submitApprovals}
                    disabled={isSubmittingApprovals}
                  >
                    {isSubmittingApprovals ? "Submitting..." : "Submit"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="shrink-0 border-t p-4">
        <PromptInput
          onSubmit={(message) => handleSendMessage(message.text)}
          className="max-w-3xl mx-auto"
        >
          <PromptInputTextarea
            placeholder={
              hasPendingTools
                ? "Respond to pending approvals..."
                : isLoading
                  ? "Waiting for response..."
                  : "Ask anything..."
            }
            disabled={isLoading || hasPendingTools}
          />
          <PromptInputFooter>
            <PromptInputTools>
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger />
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
            </PromptInputTools>
            <PromptInputSubmit
              disabled={isLoading || hasPendingTools}
              status={isLoading ? "streaming" : "ready"}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </>
  );
}

// ============================================================================
// Main ChatDefault Base Component
// ============================================================================

export function ChatDefault() {
  const { currentBlueprint } = useBlueprint();
  const { configProvider, storageAdapter } = useAdapters();
  const { currentThread, createThread, loadThreads, updateThreadTitle } =
    useThreadStore();

  const [transport, setTransport] = useState<ChimeraTransport | null>(null);
  const [initialMessages, setInitialMessages] = useState<UIMessage[]>([]);
  const [artifactOpen, _setArtifactOpen] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);

  // Generate title for thread after first message is sent
  const generateTitleForThread = useCallback(
    async (threadId: string, userPrompt: string) => {
      try {
        const backendUrl = await configProvider.getBackendUrl();
        console.log("[ChatDefault] Generating title for thread:", threadId);

        const title = await generateTitleFromPrompt(backendUrl, userPrompt);
        console.log("[ChatDefault] Generated title:", title);

        await updateThreadTitle(threadId, title);
      } catch (error) {
        console.error("[ChatDefault] Failed to generate title:", error);
        // Non-fatal - thread continues to work without generated title
      }
    },
    [configProvider, updateThreadTitle]
  );

  // Create new chat with current blueprint and queue the message
  const handleNewChatWithMessage = async (messageText: string) => {
    if (!currentBlueprint) return;

    try {
      setPendingMessage(messageText);
      await createThread(currentBlueprint.blueprintJson);
      await loadThreads();
    } catch (error) {
      console.error("[ChatDefault] Failed to create thread:", error);
      setPendingMessage(null);
    }
  };

  // Create new chat without a message (from sidebar button)
  const handleNewChat = async () => {
    if (!currentBlueprint) return;

    try {
      await createThread(currentBlueprint.blueprintJson);
      await loadThreads();
    } catch (error) {
      console.error("[ChatDefault] Failed to create thread:", error);
    }
  };

  // Initialize transport when thread changes
  useEffect(() => {
    if (!currentThread) {
      setTransport(null);
      setInitialMessages([]);
      return;
    }

    const initTransport = async () => {
      const backendUrl = await configProvider.getBackendUrl();

      const newTransport = new ChimeraTransport({
        threadId: currentThread.metadata.thread_id,
        backendUrl,
        storageAdapter,
        onEventsAccumulated: async (events) => {
          console.log(`[ChatDefault] Accumulated ${events.length} events`);
        },
      });

      await newTransport.loadHistory();

      const threadProtocol = newTransport.getThreadProtocol();
      if (threadProtocol.length > 0) {
        const events = threadProtocol.slice(1);
        const hydrated = hydrateFromEvents(events);
        setInitialMessages(hydrated);
      } else {
        setInitialMessages([]);
      }

      setTransport(newTransport);
    };

    initTransport();
  }, [currentThread, configProvider, storageAdapter]);

  const isNewChat = !currentThread;

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Sidebar */}
      <Sidebar onNewChat={handleNewChat} />

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {isNewChat ? (
          // New Chat State: Centered headline + prompt input
          <div className="flex-1 flex flex-col items-center justify-center px-4">
            <div className="w-full max-w-2xl">
              <TypingHeadline />
              <PromptInput
                onSubmit={async (message) => {
                  if (message.text.trim()) {
                    await handleNewChatWithMessage(message.text);
                  }
                }}
                className="w-full"
              >
                <PromptInputTextarea placeholder="Ask anything..." />
                <PromptInputFooter>
                  <PromptInputTools>
                    <PromptInputActionMenu>
                      <PromptInputActionMenuTrigger />
                      <PromptInputActionMenuContent>
                        <PromptInputActionAddAttachments />
                      </PromptInputActionMenuContent>
                    </PromptInputActionMenu>
                  </PromptInputTools>
                  <PromptInputSubmit status="ready" />
                </PromptInputFooter>
              </PromptInput>
            </div>
          </div>
        ) : transport ? (
          // Active Chat State
          <ChatContent
            transport={transport}
            initialMessages={initialMessages}
            pendingMessage={pendingMessage}
            onPendingMessageSent={() => {
              // Trigger title generation for new threads (no existing title)
              if (
                pendingMessage &&
                currentThread &&
                !currentThread.metadata.title
              ) {
                generateTitleForThread(
                  currentThread.metadata.thread_id,
                  pendingMessage
                );
              }
              setPendingMessage(null);
            }}
          />
        ) : (
          // Loading state
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            Loading conversation...
          </div>
        )}
      </main>

      {/* Artifact Panel - Animated (hidden for now) */}
      <div
        className={cn(
          "shrink-0 border-l bg-muted/30 transition-all duration-300 ease-out overflow-hidden",
          artifactOpen ? "w-[500px]" : "w-0"
        )}
      >
        <div className="w-[500px] h-full p-4">
          <Artifact className="h-full">
            <ArtifactHeader>
              <div>
                <ArtifactTitle>Generated Content</ArtifactTitle>
                <ArtifactDescription>
                  AI-generated artifact preview
                </ArtifactDescription>
              </div>
            </ArtifactHeader>
            <ArtifactContent className="flex items-center justify-center text-muted-foreground">
              <div className="text-center space-y-2">
                <div className="size-16 rounded-full bg-muted/50 flex items-center justify-center mx-auto">
                  <Sparkles className="size-8 text-muted-foreground/50" />
                </div>
                <p className="text-sm">Artifact content will appear here</p>
              </div>
            </ArtifactContent>
          </Artifact>
        </div>
      </div>
    </div>
  );
}

export default ChatDefault;
