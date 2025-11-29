import { Header } from "@chimera/core/components/Header";
import { ChatDefault } from "@chimera/core/bases/chat-default";
import { BlueprintProvider } from "@chimera/core/providers/BlueprintProvider";

export default function App() {
  return (
    <BlueprintProvider>
      <div className="flex flex-col h-screen bg-background text-foreground">
        <Header />
        <ChatDefault />
      </div>
    </BlueprintProvider>
  );
}
