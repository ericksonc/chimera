import { useCallback } from "react";
import { useBlueprint } from "../providers/BlueprintProvider";
import { useTheme } from "../hooks/useTheme";
import { Avatar, AvatarFallback } from "./ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Button } from "./ui/button";
import {
  ChevronDown,
  LogOut,
  Moon,
  Settings,
  Sun,
  User,
  UserCircle,
} from "lucide-react";

function ChimeraLogo() {
  return (
    <span
      className="text-xl font-light tracking-wide select-none"
      style={{
        fontFamily: "'Inter', sans-serif",
        color: "transparent",
        WebkitTextStroke: "1px oklch(0.82 0.17 171)",
        textShadow: "0 0 20px oklch(0.82 0.17 171 / 30%)",
      }}
    >
      Chimera
    </span>
  );
}

function NavDropdown({ label }: { label: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-1 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors rounded-md hover:bg-muted/50">
        {label}
        <ChevronDown className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem>Lorem ipsum</DropdownMenuItem>
        <DropdownMenuItem>Dolor sit amet</DropdownMenuItem>
        <DropdownMenuItem>Consectetur</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ModeToggle() {
  const { isDark, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      <Sun className="h-[1.2rem] w-[1.2rem] scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
      <Moon className="absolute h-[1.2rem] w-[1.2rem] scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}

export function Header() {
  const { currentBlueprintId, setCurrentBlueprintId, blueprints } =
    useBlueprint();

  // Window drag handler for Tauri
  const handleMouseDown = useCallback(async (e: React.MouseEvent) => {
    // Only drag on direct header clicks, not on interactive elements
    if ((e.target as HTMLElement).closest("button, select, [role='combobox']"))
      return;

    try {
      // Dynamic import to avoid issues in non-Tauri environments
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().startDragging();
    } catch {
      // Not in Tauri environment, ignore
    }
  }, []);

  return (
    <header
      className="flex h-14 shrink-0 items-center justify-between border-b px-4 pl-[88px] select-none cursor-default"
      onMouseDown={handleMouseDown}
    >
      <div className="flex items-center gap-4">
        <ChimeraLogo />

        <Select
          value={currentBlueprintId ?? undefined}
          onValueChange={setCurrentBlueprintId}
        >
          <SelectTrigger className="w-[160px] h-8 text-sm">
            <SelectValue placeholder="Select blueprint" />
          </SelectTrigger>
          <SelectContent>
            {blueprints.map((blueprint) => (
              <SelectItem key={blueprint.id} value={blueprint.id}>
                {blueprint.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <NavDropdown label="Resources" />
        <NavDropdown label="Settings" />
        <NavDropdown label="Help" />
      </div>

      <div className="flex items-center gap-3">
        <ModeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 px-2.5 py-1.5 rounded-full border border-foreground/20 hover:bg-muted/50 transition-colors cursor-pointer">
            <span className="text-sm text-muted-foreground">User</span>
            <Avatar className="size-7">
              <AvatarFallback className="bg-muted text-muted-foreground">
                <User className="size-3.5" />
              </AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem>
              <UserCircle className="mr-2 size-4" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings className="mr-2 size-4" />
              Account settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <LogOut className="mr-2 size-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
