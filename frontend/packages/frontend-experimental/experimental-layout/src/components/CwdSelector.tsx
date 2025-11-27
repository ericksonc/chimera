import { useState } from "react";
import { Input } from "@chimera/core/components/ui/input";
import { FolderIcon } from "lucide-react";

interface CwdSelectorProps {
  value: string;
  onChange: (value: string) => void;
}

export function CwdSelector({ value, onChange }: CwdSelectorProps) {
  const [inputValue, setInputValue] = useState(value);

  const handleBlur = () => {
    onChange(inputValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      onChange(inputValue);
    }
  };

  return (
    <div className="flex items-center gap-2 w-full max-w-md">
      <div className="flex items-center gap-2 text-muted-foreground">
        <FolderIcon className="size-4" />
        <span className="text-sm font-medium whitespace-nowrap">Working Directory:</span>
      </div>
      <Input
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        className="h-8 font-mono text-xs"
        placeholder="/path/to/project"
      />
    </div>
  );
}
