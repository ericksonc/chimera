# Implementation Plan: Slash Commands for cli_textual

## Overview
Replace ctrl-key shortcuts with slash commands that support fuzzy autocomplete and grayed-out suggestions. Also change initial blueprint loading to always use kimi-engineer.

## Architecture Changes

### 1. New File: `cli_textual/slash_commands.py`
Create a dedicated module for slash command handling:

```python
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from textual.suggester import Suggester


@dataclass
class SlashCommand:
    """Represents a slash command with shortcut and handler."""
    name: str           # Full command name (e.g., "blueprints")
    shortcut: str       # Shortcut letter (e.g., "b")
    description: str    # Help text for the command
    handler: Callable   # Function to execute when command is invoked


class SlashCommandSuggester(Suggester):
    """Provides fuzzy autocomplete suggestions for slash commands."""

    def __init__(self, commands: Dict[str, SlashCommand]):
        super().__init__(case_sensitive=False)
        self.commands = commands

    async def get_suggestion(self, value: str) -> Optional[str]:
        """Return command suggestion based on input value."""
        if not value.startswith('/'):
            return None

        # Remove the slash for matching
        query = value[1:]

        # If empty, suggest the first command
        if not query:
            return list(self.commands.keys())[0]

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
        """Check if all chars in query appear in order in target (case-insensitive)."""
        query_idx = 0
        query_lower = query.lower()
        target_lower = target.lower()

        for char in target_lower:
            if query_idx < len(query_lower) and char == query_lower[query_idx]:
                query_idx += 1

        return query_idx == len(query_lower)


# Command registry
SLASH_COMMANDS = {
    "/blueprints": SlashCommand(
        name="blueprints",
        shortcut="b",
        description="Select a blueprint",
        handler=None  # Will be set by app
    ),
    "/resume": SlashCommand(
        name="resume",
        shortcut="r",
        description="Resume a conversation",
        handler=None
    ),
    "/threads": SlashCommand(
        name="threads",
        shortcut="t",
        description="List all conversation threads",
        handler=None
    ),
    "/clear": SlashCommand(
        name="clear",
        shortcut="c",
        description="Clear current conversation",
        handler=None
    ),
    "/new": SlashCommand(
        name="new",
        shortcut="n",
        description="Start a new conversation",
        handler=None
    ),
    "/help": SlashCommand(
        name="help",
        shortcut="h",
        description="Show available commands",
        handler=None
    ),
    "/quit": SlashCommand(
        name="quit",
        shortcut="q",
        description="Quit the application",
        handler=None
    ),
}
```

### 2. Modify `cli_textual/app.py`

#### A. Update imports
```python
from textual.suggester import Suggester
from cli_textual.slash_commands import SlashCommand, SlashCommandSuggester, SLASH_COMMANDS
```

#### B. Update Input widget in compose()
```python
def compose(self) -> ComposeResult:
    """Create the UI layout."""
    # Scrollable chat history
    with VerticalScroll(id="chat-view"):
        yield Markdown("Welcome to Chimera v4! Loading session...")

    # Input with slash command suggestions
    yield Input(
        placeholder="Type your message or /command...",
        suggester=SlashCommandSuggester(SLASH_COMMANDS)
    )

    # Status line
    yield Static(id="status-line", classes="status-line")
```

#### C. Add slash command handling
```python
@on(Input.Submitted)
async def handle_input(self, event: Input.Submitted) -> None:
    """Handle when user submits input."""
    if not event.value.strip():
        return

    if not self.current_session:
        self.notify("No active session!", severity="error")
        return

    # Check for slash commands
    if event.value.startswith('/'):
        await self._handle_slash_command(event.value)
        event.input.clear()
        return

    # Regular message handling (existing code)
    chat_view = self.query_one("#chat-view", VerticalScroll)
    user_text = event.value

    # Clear the input
    event.input.clear()

    # Add user's message to chat
    await chat_view.mount(UserMessage(f"**You:** {user_text}"))

    # Mount ThinkingIndicator immediately
    await self._show_thinking()

    # Send message in background
    self.process_message_async(user_text)

async def _handle_slash_command(self, command_text: str):
    """Parse and execute slash command."""
    # Remove leading slash and whitespace
    cmd = command_text[1:].strip().lower()

    if not cmd:
        self.notify("Empty command. Type /help for available commands.", severity="warning")
        return

    # Find matching command
    for cmd_str, command in SLASH_COMMANDS.items():
        if cmd == command.name or cmd == command.shortcut:
            # Execute handler
            if command.handler:
                command.handler()
            else:
                # Default handlers
                if cmd in ['blueprints', 'b']:
                    self.action_select_blueprint()
                elif cmd in ['resume', 'r']:
                    self.action_resume_thread()
                elif cmd in ['threads', 't']:
                    self._show_threads()
                elif cmd in ['clear', 'c']:
                    self._clear_conversation()
                elif cmd in ['new', 'n']:
                    self._start_new_conversation()
                elif cmd in ['help', 'h']:
                    self._show_help()
                elif cmd in ['quit', 'q']:
                    self.action_quit()
            return

    self.notify(f"Unknown command: {command_text}. Type /help for available commands.", severity="error")

def _show_help(self):
    """Display available slash commands."""
    help_text = "**Available Commands:**\n\n"
    for cmd_str, cmd in SLASH_COMMANDS.items():
        help_text += f"**{cmd_str}** (/{cmd.shortcut}) - {cmd.description}\n"

    chat_view = self.query_one("#chat-view", VerticalScroll)
    self.call_after_refresh(
        chat_view.mount, AssistantMessage(help_text)
    )

def _show_threads(self):
    """Display list of conversation threads."""
    threads = self.session_manager.list_threads()
    if not threads:
        self.notify("No threads found.", severity="warning")
        return

    threads_text = "**Available Threads:**\n\n"
    for thread in threads:
        threads_text += f"**{thread['id']}** - {thread.get('name', 'Unnamed')}\n"

    chat_view = self.query_one("#chat-view", VerticalScroll)
    self.call_after_refresh(
        chat_view.mount, AssistantMessage(threads_text)
    )

def _clear_conversation(self):
    """Clear the current conversation view."""
    chat_view = self.query_one("#chat-view", VerticalScroll)
    # Keep the welcome/system messages, remove user/assistant messages
    self.call_after_refresh(
        chat_view.query(UserMessage).remove
    )
    self.call_after_refresh(
        chat_view.query(AssistantMessage).remove
    )
    self.call_after_refresh(
        chat_view.query(ThinkingMessage).remove
    )
    self.call_after_refresh(
        chat_view.query(ToolCallMessage).remove
    )
    self.call_after_refresh(
        chat_view.query(ToolResultMessage).remove
    )
    self.notify("Conversation cleared.", severity="information")

def _start_new_conversation(self):
    """Start a new conversation session."""
    # This will reload the current blueprint fresh
    if self.current_session:
        # Get current blueprint data
        current_blueprint = self.current_session.blueprint_data
        # Start new session with same blueprint
        self.current_session = self.session_manager.start_new_session(current_blueprint)

        # Clear the chat view
        self._clear_conversation()

        # Show confirmation
        bp_name = self._extract_blueprint_name(current_blueprint)
        chat_view = self.query_one("#chat-view", VerticalScroll)
        self.call_after_refresh(
            chat_view.mount,
            AssistantMessage(f"Started new conversation with blueprint: **{bp_name}**")
        )
    else:
        self.notify("No active session to restart.", severity="warning")
```

#### D. Modify initialize_session() to always load kimi-engineer
```python
async def initialize_session(self):
    """Initialize the chat session with kimi-engineer blueprint."""
    # Always load kimi-engineer blueprint
    kimi_blueprint_path = self.blueprints_dir / "kimi-engineer.json"

    chat_view = self.query_one("#chat-view", VerticalScroll)
    # Clear initial message
    await chat_view.query(Markdown).remove()

    if kimi_blueprint_path.exists():
        try:
            import json
            with open(kimi_blueprint_path) as f:
                blueprint_data = json.load(f)

            self.current_session = self.session_manager.start_new_session(blueprint_data)

            # Extract blueprint name
            bp_name = self._extract_blueprint_name(blueprint_data)
            self._update_status_line(bp_name)

            await chat_view.mount(
                AssistantMessage(f"Started session with blueprint: **{bp_name}**")
            )
        except Exception as e:
            self.notify(f"Error loading kimi-engineer blueprint: {e}", severity="error")
            # Fall back to blueprint selection
            self.action_select_blueprint()
    else:
        self.notify("kimi-engineer blueprint not found!", severity="error")
        # Fall back to blueprint selection
        self.action_select_blueprint()
```

#### E. Remove ctrl-key bindings (optional)
```python
BINDINGS = [
    ("ctrl+q", "quit", "Quit"),
    # Remove ctrl+b and ctrl+r since we have slash commands now
]
```

### 3. Update SessionManager (if needed)

#### A. Modify `cli/session.py`
Remove or modify the last blueprint persistence logic:

```python
class SessionManager:
    def __init__(self, cli_dir: Path, blueprints_dir: Path):
        # ... existing code ...

        # Remove or comment out last blueprint loading
        # self.config = CLIConfig.load(self.config_file)

    def get_last_used_blueprint(self):
        """Return None to force kimi-engineer loading."""
        return None  # Always return None to use default

    # Or remove this method entirely and update app.py to not call it
```

### 4. Update CLIConfig (if needed)

#### A. Modify `cli/config.py`
Remove last blueprint tracking:

```python
@dataclass
class CLIConfig:
    """CLI configuration settings."""
    # Remove these fields:
    # last_blueprint_path: Optional[str] = None
    # last_blueprint_name: Optional[str] = None
    # last_blueprint_file: Optional[str] = None

    # Keep other settings if needed
    api_url: str = "http://localhost:8000"
```

## Testing Checklist

### 1. Slash Command Autocomplete
- [ ] Type `/` → see first command suggestion in gray
- [ ] Type `/b` → see `/blueprints` in gray
- [ ] Type `/blu` → see `/blueprints` in gray (fuzzy match)
- [ ] Type `/blue` → see `/blueprints` in gray
- [ ] Press right arrow to accept suggestion
- [ ] Press Enter to execute command

### 2. Command Execution
- [ ] `/blueprints` opens blueprint selection screen
- [ ] `/b` opens blueprint selection screen (shortcut)
- [ ] `/resume` opens thread resume screen
- [ ] `/r` opens thread resume screen (shortcut)
- [ ] `/help` shows command list
- [ ] `/h` shows command list (shortcut)
- [ ] `/quit` quits the application
- [ ] `/q` quits the application (shortcut)
- [ ] Unknown commands show error notification

### 3. Blueprint Loading
- [ ] App starts with kimi-engineer blueprint loaded
- [ ] Status line shows "Kimi Engineer" as active blueprint
- [ ] No persistence of last used blueprint
- [ ] Can still change blueprints via /blueprints command

### 4. Regular Messages
- [ ] Non-slash messages work normally
- [ ] Messages without leading `/` go to AI as before
- [ ] Streaming responses work correctly

## Visual Design Notes

- Suggestions appear in muted gray automatically via Textual's `input--suggestion` CSS class
- No custom styling needed - Textual handles this natively
- Suggestion appears after the cursor, showing the full command
- User can accept with right arrow or continue typing

## Fallback Behavior

- If kimi-engineer.json is missing, show error and fall back to blueprint selection
- If slash command is unknown, show error with help suggestion
- Regular messages (no leading `/`) work exactly as before

## Migration Notes

- Remove or comment out ctrl+b and ctrl+r key bindings
- Update any documentation mentioning ctrl-key shortcuts
- The Input widget's built-in suggestion system handles the grayed-out text automatically
