"""Main CLI application for Chimera v4.

Entry point for the command-line interface.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

from .session import SessionManager, ChatSession
from .effects.display import Display
from .ui.prompt import PromptInterface, StreamingDisplay
from .ui.blueprint_selector import BlueprintSelector
from .ui.thread_resume import ThreadResume


class ChimeraCLI:
    """Main CLI application."""

    def __init__(self, project_root: Path):
        """Initialize CLI application.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = Path(project_root)
        self.cli_dir = self.project_root / "cli"
        self.blueprints_dir = self.project_root / "blueprints"

        # Initialize components
        self.session_manager = SessionManager(self.cli_dir, self.blueprints_dir)
        self.display = Display()
        self.prompt = PromptInterface(self.display)
        self.blueprint_selector = BlueprintSelector(self.display)
        self.thread_resume = ThreadResume(self.display)

        # Current session
        self.current_session: Optional[ChatSession] = None

    async def run(self):
        """Run the CLI application."""
        # Show header
        self.display.clear()
        self.display.show_header()
        self.display.console.print()

        # Check for last used blueprint or start with selection
        last_blueprint = self.session_manager.get_last_used_blueprint()

        if last_blueprint:
            # Start with last blueprint
            self.current_session = self.session_manager.start_new_session(last_blueprint)
            await self.chat_loop()
        else:
            # No last blueprint - show selection
            await self.select_blueprint()

    async def select_blueprint(self):
        """Handle blueprint selection."""
        blueprints = self.session_manager.list_blueprints()

        if not blueprints:
            self.prompt.display_error("No blueprints found in blueprints/ directory")
            return

        selected_data = self.blueprint_selector.show_blueprints(blueprints)

        if selected_data:
            # Find the file path for this blueprint
            for bp in blueprints:
                if bp["blueprint_data"] == selected_data:
                    self.session_manager.config.last_blueprint_path = bp["file_path"]
                    break

            # Start new session
            self.current_session = self.session_manager.start_new_session(selected_data)
            await self.chat_loop()

    async def resume_thread(self):
        """Handle thread resume."""
        threads = self.session_manager.list_threads()

        if not threads:
            self.prompt.display_error("No saved conversations found")
            return

        thread_id = self.thread_resume.show_threads(threads)

        if thread_id:
            # Resume session
            self.current_session = self.session_manager.resume_session(thread_id)

            # Show preview
            events = self.current_session.get_events()
            self.thread_resume.show_thread_preview(events)

            await self.chat_loop()

    async def chat_loop(self):
        """Main chat loop."""
        if not self.current_session:
            return

        self.display.console.print("[dim]Type /help for commands, /quit to exit[/dim]\n")

        while True:
            try:
                # Get user input
                user_input = await self.prompt.get_input()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    command = user_input[1:].strip().lower()

                    if command in ["quit", "exit", "q"]:
                        self.display.console.print("[dim]Goodbye![/dim]")
                        break

                    elif command == "blueprint":
                        await self.select_blueprint()
                        break  # Exit current session

                    elif command == "resume":
                        await self.resume_thread()
                        break  # Exit current session

                    elif command == "clear":
                        self.display.clear()
                        self.display.show_header()

                    elif command == "help":
                        self.show_help()

                    elif command == "save":
                        self.current_session.save()
                        self.display.console.print("[green]✓ Conversation saved[/green]")

                    else:
                        self.prompt.display_error(f"Unknown command: /{command}")

                    continue

                # Display user message
                self.prompt.display_user_message(user_input)

                # Create streaming display
                streaming = StreamingDisplay(self.prompt)

                # Show thinking indicator
                thinking = self.display.show_thinking()

                # Send message and process response
                try:
                    thinking.__enter__()

                    await self.current_session.send_message(
                        user_input,
                        on_text_delta=lambda d: (thinking.__exit__(None, None, None), streaming.on_text_delta(d)) if thinking else streaming.on_text_delta(d),
                        on_thinking_delta=streaming.on_thinking_delta,
                        on_tool_call=streaming.on_tool_call,
                        on_tool_result=streaming.on_tool_result
                    )

                    # Finish display
                    streaming.finish_text()

                except Exception as e:
                    thinking.__exit__(None, None, None)
                    self.prompt.display_error(f"Error sending message: {e}")

            except KeyboardInterrupt:
                self.display.console.print("\n[dim]Interrupted. Goodbye![/dim]")
                break
            except EOFError:
                break

    def show_help(self):
        """Show help message."""
        help_text = """
[bold]Available Commands:[/bold]

  /help         Show this help message
  /quit         Exit the application
  /blueprint    Select a different blueprint
  /resume       Resume a previous conversation
  /clear        Clear the screen
  /save         Manually save the conversation

[bold]Usage:[/bold]

  Simply type your message and press Enter to chat.
  The agent will respond with thinking indicators and visual effects.
        """
        self.display.console.print(help_text)


async def main():
    """Main entry point."""
    # Get project root (parent of cli directory)
    project_root = Path(__file__).parent.parent

    cli = ChimeraCLI(project_root)

    try:
        await cli.run()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
