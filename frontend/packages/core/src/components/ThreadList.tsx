import { useEffect } from "react";
import { useThreadStore } from "../stores/threadStore";

export function ThreadList() {
  const { threads, currentThread, isLoading, error, loadThreads, loadThread } =
    useThreadStore();

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const handleSelectThread = async (threadId: string) => {
    try {
      await loadThread(threadId);
    } catch (error) {
      console.error("Failed to load thread:", error);
    }
  };

  if (isLoading && threads.length === 0) {
    return (
      <div className="p-4">
        <p className="text-sm text-muted-foreground">Loading threads...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-destructive">Error: {error}</p>
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className="p-4">
        <p className="text-sm text-muted-foreground">
          No conversations yet. Create one to get started!
        </p>
      </div>
    );
  }

  return (
    <div className="p-2 space-y-1">
      <h3 className="text-sm font-semibold px-2 py-1 text-muted-foreground">
        Conversations
      </h3>
      {threads.map((thread) => {
        const isActive = currentThread?.metadata.thread_id === thread.thread_id;
        const displayTitle = thread.title || "Untitled conversation";
        const date = new Date(thread.updated_at).toLocaleDateString();

        return (
          <button
            key={thread.thread_id}
            onClick={() => handleSelectThread(thread.thread_id)}
            className={`
              w-full text-left px-3 py-2 rounded-md transition-colors
              ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-muted text-foreground"
              }
            `}
          >
            <div className="text-sm font-medium truncate">{displayTitle}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{date}</div>
          </button>
        );
      })}
    </div>
  );
}
