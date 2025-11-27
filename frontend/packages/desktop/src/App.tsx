import { useState, useEffect } from "react";
import { ChimeraChat } from "@chimera/core/components/ChimeraChat";
import { BlueprintSelector } from "@chimera/core/components/BlueprintSelector";
import { ThreadList } from "@chimera/core/components/ThreadList";
import { useThreadStore } from "@chimera/core";
import { useTheme } from "@chimera/core/hooks/useTheme";

export default function App() {
  const [showBlueprintSelector, setShowBlueprintSelector] = useState(false);
  const { currentThread: _currentThread } = useThreadStore();
  const { theme, isDark, setTheme } = useTheme();

  // Debug theme state
  useEffect(() => {
    console.log("[App] Theme state changed:", { theme, isDark });
    console.log(
      "[App] HTML classList:",
      document.documentElement.classList.toString()
    );
    console.log(
      "[App] Computed background color:",
      getComputedStyle(document.documentElement).getPropertyValue(
        "--background"
      )
    );
  }, [theme, isDark]);

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <div className="w-80 border-r flex flex-col">
        {/* Header */}
        <div className="p-4 border-b">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-xl font-bold">Chimera Desktop</h1>
              <p className="text-sm text-muted-foreground">
                Multi-Agent System
              </p>
            </div>
            <button
              onClick={() => {
                const newTheme =
                  theme === "dark"
                    ? "light"
                    : theme === "light"
                      ? "auto"
                      : "dark";
                console.log(
                  "[App] Switching theme from",
                  theme,
                  "to",
                  newTheme
                );
                console.log(
                  "[App] HTML has dark class:",
                  document.documentElement.classList.contains("dark")
                );
                setTheme(newTheme);
              }}
              className="text-xs px-2 py-1 rounded border hover:bg-secondary"
              title={`Click to cycle theme. HTML dark class: ${document.documentElement.classList.contains("dark")}`}
            >
              {theme} {isDark ? "🌙" : "☀️"}
            </button>
          </div>
        </div>

        {/* New Thread Button */}
        <div className="p-4 border-b">
          <button
            onClick={() => setShowBlueprintSelector(!showBlueprintSelector)}
            className="
              w-full px-4 py-2 rounded-lg
              bg-primary text-primary-foreground
              hover:bg-primary/90
              transition-colors
              text-sm font-medium
            "
          >
            {showBlueprintSelector ? "Hide Blueprints" : "+ New Conversation"}
          </button>
        </div>

        {/* Blueprint Selector or Thread List */}
        <div className="flex-1 overflow-y-auto">
          {showBlueprintSelector ? <BlueprintSelector /> : <ThreadList />}
        </div>

        {/* Footer */}
        <div className="p-4 border-t text-xs text-muted-foreground">
          <div>Backend: localhost:33003</div>
          <div>Data: ~/chimera-desktop/</div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1">
        <ChimeraChat />
      </div>
    </div>
  );
}
