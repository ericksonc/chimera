import { useState, FormEvent } from "react";
import { Send } from "lucide-react";
import { cn } from "../../lib/utils";

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSubmit,
  disabled = false,
  placeholder = "Type a message...",
}: ChatInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSubmit(input);
      setInput("");
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex gap-2 p-4 border-t border-border"
    >
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={cn(
          "flex-1 px-4 py-2 rounded-lg",
          "bg-input text-foreground",
          "border border-border",
          "focus:outline-none focus:ring-2 focus:ring-ring",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      />
      <button
        type="submit"
        disabled={disabled || !input.trim()}
        className={cn(
          "px-4 py-2 rounded-lg",
          "bg-primary text-primary-foreground",
          "hover:opacity-90",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-opacity"
        )}
      >
        <Send className="w-5 h-5" />
      </button>
    </form>
  );
}
