import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  ConversationEmptyState,
} from "@chimera/core/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
} from "@chimera/core/components/ai-elements/message";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputSubmit,
  PromptInputHeader,
  PromptInputBody,
  PromptInputFooter,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  PromptInputAttachments,
  PromptInputAttachment,
} from "@chimera/core/components/ai-elements/prompt-input";
import { Response } from "@chimera/core/components/ai-elements/response";
import { Avatar, AvatarFallback, AvatarImage } from "@chimera/core/components/ui/avatar";
import { useChimeraChat } from "@chimera/core/hooks/useChimeraChat";
import { ChimeraTransport } from "@chimera/core/lib/chimera-transport";
import type { ThreadMetadata } from "@chimera/core/stores/threadStore";
import type { UIMessage } from "ai";

interface ChatProps {
  transport: ChimeraTransport;
  currentThread: { metadata: ThreadMetadata; events: any[] };
  initialMessages: UIMessage[];
  cwd: string;
}

export function Chat({ transport, currentThread, initialMessages, cwd }: ChatProps) {
  const {
    messages,
    isLoading,
    handleSendMessage,
  } = useChimeraChat({
    transport,
    currentThread,
    initialMessages,
  });

  return (
    <div className="flex flex-col h-full">
      <Conversation className="flex-1">
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState
              title="Ready to chat"
              description={`Working in: ${cwd}`}
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
                  />
                  <AvatarFallback>{message.role === "user" ? "US" : "AI"}</AvatarFallback>
                </Avatar>
                <MessageContent>
                  {message.parts.map((part, index) => {
                    if (part.type === "text") {
                      return <Response key={index}>{part.text}</Response>;
                    }
                    // TODO: Add Tool and Reasoning support here if needed for full parity
                    // For now, focusing on basic chat + CWD
                    return null;
                  })}
                </MessageContent>
              </Message>
            ))
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="p-4 border-t">
        <PromptInput
          onSubmit={(message) => {
            handleSendMessage(message.text, { clientContext: { cwd } });
          }}
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
              placeholder="Type a message..."
              disabled={isLoading}
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
            <PromptInputSubmit disabled={isLoading} status={isLoading ? "streaming" : "ready"} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
