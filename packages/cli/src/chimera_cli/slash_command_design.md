# Slash Command System Design for cli_textual

## Overview
Replace ctrl-key shortcuts with slash commands that support fuzzy autocomplete and grayed-out suggestions.

## Current State
- Uses `Input` widget for user input
- Commands accessed via ctrl-key bindings: ^b (blueprints), ^r (resume)
- No autocomplete or suggestion system

## Proposed Design

### 1. Command Registry
```python
class SlashCommand:
    name: str           # Full command name (e.g., "blueprints")
    shortcut: str       # Shortcut (e.g., "b")
    description: str    # Help text
    handler: Callable   # Function to call

# Registry
SLASH_COMMANDS = {
    "/blueprints": SlashCommand("blueprints", "b", "Select a blueprint", handle_blueprints),
    "/resume": SlashCommand("resume", "r", "Resume a conversation", handle_resume),
    "/threads": SlashCommand("threads", "t", "List all conversation threads", handle_threads),
    "/clear": SlashCommand("clear", "c", "Clear current conversation", handle_clear),
    "/new": SlashCommand("new", "n", "Start a new conversation", handle_new),
    "/help": SlashCommand("help", "h", "Show available commands", handle_help),
    "/quit": SlashCommand("quit", "q", "Quit the application", handle_quit),
}
```

### 2. Custom Suggester
```python
class SlashCommandSuggester(Suggester):
    """Provides fuzzy autocomplete for slash commands."""

    def __init__(self, commands: Dict[str, SlashCommand]):
        super().__init__(case_sensitive=False)
        self.commands = commands

    async def get_suggestion(self, value: str) -> str | None:
        """Return command suggestion based on input."""
        if not value.startswith('/'):
            return None

        # Remove the slash for matching
        query = value[1:]

        # Exact match on full command or shortcut
        for cmd_str, cmd in self.commands.items():
            if query == cmd.name or query == cmd.shortcut:
                return cmd_str

        # Fuzzy match on command name
        for cmd_str, cmd in self.commands.items():
            if self._fuzzy_match(query, cmd.name):
                return cmd_str

        return None

    def _fuzzy_match(self, query: str, target: str) -> bool:
        """Simple fuzzy matching - all chars in query appear in order in target."""
        query_idx = 0
        for char in target:
            if query_idx < len(query) and char.lower() == query[query_idx].lower():
                query_idx += 1
        return query_idx == len(query)
```

### 3. Input Integration
```python
# In app.py
def compose(self) -> ComposeResult:
    # ...
    yield Input(
        placeholder="Type your message or /command...",
        suggester=SlashCommandSuggester(SLASH_COMMANDS)
    )

@on(Input.Submitted)
async def handle_input(self, event: Input.Submitted) -> None:
    """Handle both regular messages and slash commands."""
    if not event.value.strip():
        return

    # Check for slash commands
    if event.value.startswith('/'):
        await self._handle_slash_command(event.value)
        event.input.clear()
        return

    # Regular message handling...

async def _handle_slash_command(self, command_text: str):
    """Parse and execute slash command."""
    # Remove leading slash
    cmd = command_text[1:].lower()

    # Find matching command
    for cmd_str, command in SLASH_COMMANDS.items():
        if cmd == command.name or cmd == command.shortcut:
            command.handler()
            return

    self.notify(f"Unknown command: {command_text}", severity="error")
```

### 4. Blueprint Loading Change
```python
# In initialize_session()
async def initialize_session(self):
    """Always load kimi-engineer blueprint."""
    # Load kimi-engineer blueprint directly
    kimi_blueprint_path = self.blueprints_dir / "kimi-engineer.json"
    if kimi_blueprint_path.exists():
        import json
        with open(kimi_blueprint_path) as f:
            blueprint_data = json.load(f)

        self.current_session = self.session_manager.start_new_session(blueprint_data)
        # ... rest of setup
    else:
        self.notify("kimi-engineer blueprint not found!", severity="error")
```

### 5. Visual Design
- Suggestions appear in muted gray (Textual's default `input--suggestion` style)
- User types `/b` → sees `/blueprints` in gray
- Pressing right arrow accepts suggestion
- Pressing Enter executes the command

## Implementation Steps
1. Create `SlashCommand` dataclass and registry
2. Implement `SlashCommandSuggester` with fuzzy matching
3. Modify `Input` widget to use suggester
4. Update `handle_input` to route slash commands
5. Change `initialize_session` to always load kimi-engineer
6. Remove last blueprint persistence from config
7. Test all command shortcuts and fuzzy matching

## Benefits
- More intuitive than ctrl-key shortcuts
- Discoverable via autocomplete
- Fuzzy search reduces typing ("/b" → "/blueprints")
- Consistent with modern CLI tools (Discord, Slack, GitHub CLI)
- Visual feedback with grayed-out suggestions
