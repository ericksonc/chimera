import { ReactNode } from "react";

interface ShellProps {
  sidebar: ReactNode;
  main: ReactNode;
  aside: ReactNode;
  header: ReactNode;
}

export function Shell({ sidebar, main, aside, header }: ShellProps) {
  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background text-foreground">
      {/* Header Area */}
      <header className="flex h-14 items-center border-b px-4">
        {header}
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar (Past Threads) */}
        <aside className="w-64 border-r bg-muted/10 hidden md:block">
          {sidebar}
        </aside>

        {/* Center (Chatbot) */}
        <main className="flex-1 flex flex-col min-w-0">
          {main}
        </main>

        {/* Right Sidebar (Artifact) */}
        <aside className="w-80 border-l bg-muted/10 hidden lg:block">
          {aside}
        </aside>
      </div>
    </div>
  );
}
