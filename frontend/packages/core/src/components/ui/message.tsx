import { cn } from "../../lib/utils";
import { useEffect, useRef } from "react";

interface MessageProps {
  role: "user" | "assistant" | "system";
  content: string;
}

export function Message({ role, content }: MessageProps) {
  const divRef = useRef<HTMLDivElement>(null);

  // Update DOM directly on content change to bypass React batching
  useEffect(() => {
    if (divRef.current) {
      const p = divRef.current.querySelector('p');
      if (p) p.textContent = content;
    }
  }, [content]);

  // Don't render system messages
  if (role === "system") return null;

  return (
    <div
      ref={divRef}
      className={cn(
        "flex w-full gap-3 p-4",
        role === "user" ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2",
          role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        <p className="text-sm whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
