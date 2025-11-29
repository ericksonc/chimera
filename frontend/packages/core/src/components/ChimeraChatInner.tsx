import {
  PromptInput,
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputAttachment,
  PromptInputAttachments,
  PromptInputBody,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "./ai-elements/prompt-input";
import { ChimeraTransport } from "../lib/chimera-transport";
import type { ThreadMetadata } from "../stores/threadStore";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  ConversationEmptyState,
} from "./ai-elements/conversation";
import { Message, MessageContent } from "./ai-elements/message";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import { Response } from "./ai-elements/response";
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "./ai-elements/tool";
import {
  Confirmation,
  ConfirmationActions,
  ConfirmationAction,
  ConfirmationTitle,
  ConfirmationRequest,
} from "./ai-elements/confirmation";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "./ai-elements/reasoning";
import { Button } from "./ui/button";
import { Alert, AlertDescription } from "./ui/alert";
import type { ToolUIPart, UIMessage } from "ai";
import { useChimeraChat } from "../hooks/useChimeraChat";
import type { ThreadProtocolEvent } from "../lib/thread-protocol";

/** Reasoning part type for extended thinking display */
interface ReasoningPart {
  type: "reasoning";
  text?: string;
  details?: string;
}

interface ChimeraChatInnerProps {
  transport: ChimeraTransport;
  currentThread: { metadata: ThreadMetadata; events: ThreadProtocolEvent[] };
  messages: UIMessage[];
}

export function ChimeraChatInner({
  transport,
  currentThread,
  messages: initialMessages,
}: ChimeraChatInnerProps) {
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
    currentThread,
    initialMessages,
  });

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="border-b px-4 py-3">
        <h2 className="text-lg font-semibold">
          {currentThread.metadata.title || "New Conversation"}
        </h2>
        <p className="text-sm text-muted-foreground">
          Thread: {currentThread.metadata.thread_id.slice(0, 8)}...
        </p>
      </div>

      {/* Messages with AI Elements Conversation */}
      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState
              title="No messages yet"
              description="Send a message to start the conversation"
            />
          ) : (
            messages.map((message) => (
              <Message key={message.id} from={message.role}>
                <Avatar className="h-8 w-8">
                  <AvatarImage
                    src={
                      message.role === "user"
                        ? "https://github.com/shadcn.png"
                        : "https://github.com/openai.png"
                    }
                    alt={message.role === "user" ? "User" : "Assistant"}
                  />
                  <AvatarFallback>
                    {message.role === "user" ? "US" : "AI"}
                  </AvatarFallback>
                </Avatar>
                <MessageContent>
                  {message.parts.map((part, index) => {
                    // Handle text parts
                    if (part.type === "text") {
                      return <Response key={index}>{part.text}</Response>;
                    }

                    // Handle tool call parts (any type starting with "tool-")
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

                            {/* Tool needs approval */}
                            {isAwaitingApproval && (
                              <Confirmation
                                approval={{ id: toolPart.toolCallId }}
                                state="approval-requested"
                              >
                                <ConfirmationTitle>
                                  <ConfirmationRequest>
                                    Do you want to execute{" "}
                                    <strong>{toolName}</strong>?
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

                            {/* Tool output (executed) */}
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

                    // Handle reasoning parts
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

                    // Fallback for unknown part types
                    return null;
                  })}
                </MessageContent>
              </Message>
            ))
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Batch Approval UI */}
      {hasPendingTools && (
        <div className="border-t bg-muted/50 px-4 py-3">
          <div className="flex flex-col gap-3">
            {approvalError && (
              <Alert variant="destructive">
                <AlertDescription>{approvalError}</AlertDescription>
              </Alert>
            )}
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {toolsNeedingApproval.length} tool
                  {toolsNeedingApproval.length !== 1 ? "s" : ""} awaiting
                  approval
                </span>
                {Object.keys(pendingApprovals).length > 0 && (
                  <span className="text-sm text-muted-foreground">
                    ({Object.keys(pendingApprovals).length} decision
                    {Object.keys(pendingApprovals).length !== 1 ? "s" : ""}{" "}
                    made)
                  </span>
                )}
              </div>
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
                    {isSubmittingApprovals
                      ? "Submitting..."
                      : "Submit Decisions"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input */}
      <PromptInput
        onSubmit={(message) => {
          // Send message with optional file attachments for multimodal input
          handleSendMessage(message.text, {
            files: message.files.length > 0 ? message.files : undefined,
          });
        }}
        className="p-4 border-t bg-background"
        globalDrop
        multiple
      >
        <PromptInputHeader>
          <PromptInputAttachments>
            {(attachment) => <PromptInputAttachment data={attachment} />}
          </PromptInputAttachments>
        </PromptInputHeader>
        <PromptInputBody>
          <PromptInputTextarea
            placeholder={
              hasPendingTools
                ? "Please respond to pending tool approvals..."
                : isLoading
                  ? "Waiting for response..."
                  : "Type a message..."
            }
            disabled={isLoading || hasPendingTools}
          />
        </PromptInputBody>
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
  );
}
