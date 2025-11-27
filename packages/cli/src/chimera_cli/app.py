#!/usr/bin/env python3
"""
Chimera v4 Textual CLI
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual import on, work  # type: ignore
from textual.app import App, ComposeResult  # type: ignore
from textual.containers import VerticalScroll  # type: ignore
from textual.widgets import Input, Markdown, Static  # type: ignore

from chimera_cli.session import ChatSession, SessionManager
from chimera_cli.screens.approval import ApprovalScreen
from chimera_cli.screens.blueprint_select import BlueprintSelectScreen
from chimera_cli.screens.model_select import ModelSelectScreen
from chimera_cli.screens.thread_resume import ThreadResumeScreen
from chimera_cli.slash_commands import SLASH_COMMANDS, SlashCommandSuggester
from chimera_cli.widgets.effects import ThinkingIndicator
from chimera_cli.widgets.messages import (
    AssistantMessage,
    ThinkingMessage,
    ToolCallMessage,
    ToolResultMessage,
    UserMessage,
)


class ChimeraApp(App):
    """Main Chimera CLI Application."""

    AUTO_FOCUS = "Input"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("escape", "halt_execution", "Stop"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }

    #chat-view {
        height: 1fr;
        background: $surface-darken-1;
    }

    Input {
        height: 3;
        background: $surface-lighten-1;
        border: tall $primary;
        margin: 0;
    }

    Input:focus {
        border: tall $accent;
    }

    .status-line {
        height: 1;
        background: $surface;
        color: $text-muted;
        content-align: center middle;
    }
    """

    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.cwd = os.getcwd()  # Capture invocation CWD
        # CLI data directory (config, threads) - in packages/cli for now
        self.cli_dir = self.project_root / "packages" / "cli" / "data"
        # Blueprints are in defs/blueprints/{name}/blueprint.json
        self.blueprints_dir = self.project_root / "defs" / "blueprints"

        # Initialize SessionManager
        self.session_manager = SessionManager(self.cli_dir, self.blueprints_dir)
        self.current_session: Optional[ChatSession] = None

        # State for streaming
        self.current_response_widget: Optional[AssistantMessage] = None
        self.current_thinking_widget: Optional[ThinkingMessage] = None
        self.streaming_active: bool = False

        # Model override (set via /model command)
        self.selected_model: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        # Scrollable chat history
        with VerticalScroll(id="chat-view"):
            yield Markdown("Welcome to Chimera v4! Loading session...")

        # Input for user messages with slash command suggestions
        yield Input(
            placeholder="Type your message or /command...",
            suggester=SlashCommandSuggester(SLASH_COMMANDS),
        )

        # Status line
        yield Static(id="status-line", classes="status-line")

    def on_mount(self) -> None:
        """Set up anchoring and start session."""
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.anchor()

        # Initialize session (using last used blueprint for now)
        self.call_after_refresh(self.initialize_session)

    def _extract_blueprint_name(self, blueprint_data: Dict[str, Any]) -> str:
        """Extract display name from blueprint data."""
        # 1. Check if it's a metadata dict (has 'name') - used in select_blueprint
        if "name" in blueprint_data:
            return str(blueprint_data["name"])

        # 2. Check inside blueprint -> space -> agents - raw JSON structure
        agents = blueprint_data.get("blueprint", {}).get("space", {}).get("agents", [])
        if agents:
            return str(agents[0].get("name", "Unknown"))

        return "Unknown"

    async def initialize_session(self):
        """Initialize the chat session with kimi-engineer blueprint."""
        # Always load kimi-engineer blueprint (defs/blueprints/kimi-engineer/blueprint.json)
        kimi_blueprint_path = self.blueprints_dir / "kimi-engineer" / "blueprint.json"

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

    def action_select_blueprint(self):
        """Show blueprint selection screen."""
        blueprints = self.session_manager.list_blueprints()

        def on_select(blueprint: Optional[Dict[str, Any]]):
            if blueprint:
                # Update config (mirroring cli/main.py logic)
                self.session_manager.config.last_blueprint_path = blueprint["file_path"]
                self.session_manager.config.last_blueprint_name = blueprint["name"]
                self.session_manager.config.last_blueprint_file = blueprint["file_name"]

                self.current_session = self.session_manager.start_new_session(
                    blueprint["blueprint_data"]
                )
                chat_view = self.query_one("#chat-view", VerticalScroll)

                async def setup_session():
                    # Clear old messages
                    await chat_view.query(Static).remove()
                    await chat_view.query(Markdown).remove()

                    bp_name = blueprint.get("name", "Unknown")
                    self._update_status_line(bp_name)

                    await chat_view.mount(
                        AssistantMessage(f"Started session with blueprint: **{bp_name}**")
                    )

                self.call_after_refresh(setup_session)

        self.push_screen(BlueprintSelectScreen(blueprints), on_select)

    def action_resume_thread(self):
        """Show thread resume screen."""
        threads = self.session_manager.list_threads()

        def on_select(thread: Optional[Dict[str, Any]]):
            if thread:
                # Resume session
                # We need to implement resume logic in SessionManager/ChatSession if not present
                # Assuming start_new_session can take a thread_id or we have resume_session
                # Checking SessionManager... it has resume_session(thread_id)
                self.current_session = self.session_manager.resume_session(thread["id"])

                chat_view = self.query_one("#chat-view", VerticalScroll)

                async def setup_resume():
                    await chat_view.query(Static).remove()  # Clear all
                    await chat_view.query(Markdown).remove()
                    await chat_view.mount(
                        AssistantMessage(f"Resumed thread: **{thread.get('id')}**")
                    )
                    # TODO: Load history into UI

                self.call_after_refresh(setup_resume)

        self.push_screen(ThreadResumeScreen(threads), on_select)

    def action_select_model(self):
        """Show model selection screen."""

        async def show_model_screen():
            try:
                models = await self._fetch_models()
                if not models:
                    self.notify("No models available", severity="warning")
                    return

                def on_select(model_id: Optional[str]):
                    if model_id:
                        self.selected_model = model_id
                        self.notify(f"Model set to: {model_id}")
                        # Update status line
                        if self.current_session:
                            bp_name = self._extract_blueprint_name(
                                self.current_session.blueprint_data or {}
                            )
                            self._update_status_line(bp_name)

                self.push_screen(ModelSelectScreen(models), on_select)
            except Exception as e:
                self.notify(f"Failed to fetch models: {e}", severity="error")

        self.call_after_refresh(show_model_screen)

    async def _fetch_models(self) -> List[Dict[str, Any]]:
        """Fetch models from the API."""
        import httpx

        server_url = self.session_manager.config.server_url.rstrip("/")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{server_url}/api/v1/models")
            response.raise_for_status()
            data = response.json()
            models: List[Dict[str, Any]] = data.get("models", [])
            return models

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        """Handle when user submits input."""
        if not event.value.strip():
            return

        if not self.current_session:
            self.notify("No active session!", severity="error")
            return

        # Check for slash commands
        if event.value.startswith("/"):
            # Use suggestion if available, otherwise use raw input
            input_widget = event.input
            command_text = input_widget._suggestion if input_widget._suggestion else event.value
            await self._handle_slash_command(command_text)
            event.input.clear()
            return

        chat_view = self.query_one("#chat-view", VerticalScroll)
        user_text = event.value

        # Clear the input
        event.input.clear()

        # Add user's message to chat
        await chat_view.mount(UserMessage(f"**You:** {user_text}"))

        # Mount ThinkingIndicator immediately (always moving)
        await self._show_thinking()

        # Send message in background
        self.process_message_async(user_text)

    @work(thread=True)
    def process_message(self, user_text: str) -> None:
        """Process message in background thread."""
        # We use the async version
        self.process_message_async(user_text)

    @work(exclusive=True)
    async def process_message_async(self, user_text: str) -> None:
        """Process message asynchronously."""
        if not self.current_session:
            return

        try:
            # Reset state for new message
            self.current_response_widget = None
            self.current_thinking_widget = None
            self.streaming_active = True

            await self.current_session.send_message(
                user_text,
                on_text_delta=self._on_text_delta,
                on_thinking_delta=self._on_thinking_delta,
                on_tool_call=self._on_tool_call,
                on_tool_result=self._on_tool_result,
                on_error=self._on_error,
                on_approval_request=self._on_approval_request,
                client_context=self._build_client_context(),
            )

            # Message done
            await self._remove_thinking()

        except Exception as e:
            self.notify(f"Error sending message: {e}", severity="error")
            await self._remove_thinking()
        finally:
            self.streaming_active = False

    # --- UI Helpers ---

    def _build_client_context(self) -> Dict[str, Any]:
        """Build client context dict for send_message."""
        ctx: Dict[str, Any] = {"cwd": self.cwd}
        if self.selected_model:
            ctx["model"] = self.selected_model
        return ctx

    async def _show_thinking(self):
        """Show thinking indicator if not already shown."""
        chat_view = self.query_one("#chat-view", VerticalScroll)
        if not chat_view.query(ThinkingIndicator):
            await chat_view.mount(ThinkingIndicator())
            chat_view.scroll_end(animate=False)

    async def _remove_thinking(self):
        """Remove thinking indicator."""
        chat_view = self.query_one("#chat-view", VerticalScroll)
        await chat_view.query(ThinkingIndicator).remove()

    async def _ensure_response_widget(self):
        """Ensure AssistantMessage widget exists and ThinkingIndicator is removed."""
        if not self.current_response_widget:
            await self._remove_thinking()
            chat_view = self.query_one("#chat-view", VerticalScroll)
            self.current_response_widget = AssistantMessage("")
            await chat_view.mount(self.current_response_widget)

    async def _ensure_thinking_widget(self):
        """Ensure ThinkingMessage widget exists."""
        if not self.current_thinking_widget:
            chat_view = self.query_one("#chat-view", VerticalScroll)
            self.current_thinking_widget = ThinkingMessage("")
            await chat_view.mount(self.current_thinking_widget)
            # Also show indicator if not present
            await self._show_thinking()

    def _update_status_line(self, blueprint_name: str):
        """Update the status line with active blueprint and model."""
        status_line = self.query_one("#status-line", Static)
        model_info = f" | Model: {self.selected_model}" if self.selected_model else ""
        status_line.update(f"Blueprint: {blueprint_name}{model_info}")

    # --- Callbacks ---

    def _on_text_delta(self, delta: str):
        # Ensure response widget exists (this removes thinking indicator)
        # We need to schedule this on the main thread if we were in a thread,
        # but process_message_async is an async worker on main thread, so we can await?
        # No, callbacks are synchronous functions called by send_message.
        # If send_message is awaited in process_message_async, these run in that context.
        # So we can use `self.call_from_thread` if needed, but here we are in async worker?
        # Textual's @work(exclusive=True) runs as a task on the loop.
        # So `_on_text_delta` is called directly.
        # However, we can't `await` in a sync callback.
        # We must use `self.call_after_refresh` or similar to schedule async UI updates
        # OR make the callback async if `send_message` supports it (it usually doesn't).
        # Actually, `send_message` in `cli/session.py` likely calls them synchronously.

        # We'll use `run_worker` to fire and forget async UI updates from sync callback
        # OR just modify non-async state and schedule update.
        # But mounting widgets is async.

        # Hack: Use `self.call_from_thread` which works even if we are on main thread
        # (it schedules a callback).
        # But `_ensure_response_widget` is async.

        # Let's define a sync wrapper that schedules the async work.
        self.call_after_refresh(self._handle_text_delta_async, delta)

    async def _handle_text_delta_async(self, delta: str):
        await self._ensure_response_widget()
        self._append_text(delta)

    def _on_thinking_delta(self, delta: str):
        self.call_after_refresh(self._handle_thinking_delta_async, delta)

    async def _handle_thinking_delta_async(self, delta: str):
        await self._ensure_thinking_widget()
        if self.current_thinking_widget:
            self.current_thinking_widget.update_text(delta)

    def _on_tool_call(self, tool_call: Dict[str, Any]):
        self.call_after_refresh(self._handle_tool_call_async, tool_call)

    async def _handle_tool_call_async(self, tool_call: Dict[str, Any]):
        # Remove thinking indicator (it will be re-added if needed)
        await self._remove_thinking()

        # Reset thinking widget so subsequent reasoning creates a new block
        self.current_thinking_widget = None

        chat_view = self.query_one("#chat-view", VerticalScroll)
        # Use toolName if available, fallback to name (some events might differ)
        name = tool_call.get("toolName", tool_call.get("name", "Unknown"))
        await chat_view.mount(ToolCallMessage(name, tool_call.get("input", {})))

        # Re-show thinking as we wait for result
        await self._show_thinking()

    def _on_tool_result(self, result: Dict[str, Any]):
        self.call_after_refresh(self._handle_tool_result_async, result)

    async def _handle_tool_result_async(self, result: Dict[str, Any]):
        await self._remove_thinking()

        # Reset thinking widget so subsequent reasoning creates a new block
        self.current_thinking_widget = None

        chat_view = self.query_one("#chat-view", VerticalScroll)

        # Extract correct keys (cli/ui/prompt.py uses toolName, output, status)
        tool_name = result.get("toolName", result.get("tool_name", "Unknown"))
        output = result.get("output", result.get("result"))
        status = result.get("status", "success")

        await chat_view.mount(ToolResultMessage(tool_name, output, status))

        # We might get more text or thinking after this
        await self._show_thinking()

    async def _on_approval_request(self, pending_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle approval request by showing screen."""
        # Create a future to wait for result
        future: asyncio.Future[Dict[str, Any]] = asyncio.Future()

        def on_dismiss(result: Dict[str, Any]):
            future.set_result(result)

        self.push_screen(ApprovalScreen(pending_tools), on_dismiss)

        # Wait for user interaction
        return await future

    def _on_error(self, error: str):
        self.notify(f"Error: {error}", severity="error")
        self.call_after_refresh(self._remove_thinking)

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
                    if cmd in ["blueprints", "b"]:
                        self.action_select_blueprint()
                    elif cmd in ["resume", "r"]:
                        self.action_resume_thread()
                    elif cmd in ["threads", "t"]:
                        self._show_threads()
                    elif cmd in ["clear", "c"]:
                        self._clear_conversation()
                    elif cmd in ["new", "n"]:
                        self._start_new_conversation()
                    elif cmd in ["help", "h"]:
                        self._show_help()
                    elif cmd in ["quit", "q"]:
                        self.action_quit()
                    elif cmd in ["model", "m"]:
                        self.action_select_model()
                return

        self.notify(
            f"Unknown command: {command_text}. Type /help for available commands.", severity="error"
        )

    def _show_help(self):
        """Display available slash commands."""
        help_text = "**Available Commands:**\n\n"
        for cmd_str, cmd in SLASH_COMMANDS.items():
            help_text += f"**{cmd_str}** (/{cmd.shortcut}) - {cmd.description}\n"

        chat_view = self.query_one("#chat-view", VerticalScroll)
        self.call_after_refresh(chat_view.mount, AssistantMessage(help_text))

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
        self.call_after_refresh(chat_view.mount, AssistantMessage(threads_text))

    def _clear_conversation(self):
        """Clear the current conversation view."""
        chat_view = self.query_one("#chat-view", VerticalScroll)
        # Keep the welcome/system messages, remove user/assistant messages
        self.call_after_refresh(chat_view.query(UserMessage).remove)
        self.call_after_refresh(chat_view.query(AssistantMessage).remove)
        self.call_after_refresh(chat_view.query(ThinkingMessage).remove)
        self.call_after_refresh(chat_view.query(ToolCallMessage).remove)
        self.call_after_refresh(chat_view.query(ToolResultMessage).remove)
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
                AssistantMessage(f"Started new conversation with blueprint: **{bp_name}**"),
            )
        else:
            self.notify("No active session to restart.", severity="warning")

    def _append_text(self, delta: str):
        """Append text to current response widget."""
        if self.current_response_widget:
            if not hasattr(self.current_response_widget, "text_buffer"):
                self.current_response_widget.text_buffer = ""

            self.current_response_widget.text_buffer += delta
            self.current_response_widget.update(self.current_response_widget.text_buffer)

    async def action_halt_execution(self) -> None:
        """Halt the currently running agent execution (triggered by ESC key)."""
        if not self.streaming_active:
            # No active streaming, nothing to halt
            return

        if not self.current_session:
            self.notify("No active session to halt", severity="warning")
            return

        # Ensure thread_id is a string (in case it's a UUID object)
        thread_id = str(self.current_session.thread_id)
        server_url = self.current_session.config.server_url.rstrip("/")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(f"{server_url}/halt", json={"thread_id": thread_id})

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "cancelled":
                    self.notify("Execution halted", severity="information")
                elif result.get("status") == "not_found":
                    self.notify("Execution already completed", severity="information")
                else:
                    self.notify(f"Unexpected response: {result}", severity="warning")

        except httpx.HTTPError as e:
            self.notify(f"Failed to halt execution: {e}", severity="error")
        except Exception as e:
            self.notify(f"Error halting execution: {e}", severity="error")


def run():
    """Entry point for chimera command."""
    # Get monorepo root by going up from packages/cli/src/chimera_cli/app.py
    # app.py -> chimera_cli -> src -> cli -> packages -> monorepo_root
    project_root = Path(__file__).parent.parent.parent.parent.parent
    app = ChimeraApp(project_root)
    app.run()


if __name__ == "__main__":
    run()
