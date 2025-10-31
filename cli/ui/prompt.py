"""Prompt interface for CLI.

Handles user input with visual effects and message display.
"""

import asyncio
from typing import Optional, Callable
from rich.console import Console
from rich.prompt import Prompt

from ..effects.display import Display


class PromptInterface:
    """Handles user input and display."""

    def __init__(self, display: Optional[Display] = None):
        """Initialize prompt interface.

        Args:
            display: Display instance (creates one if not provided)
        """
        self.display = display or Display()
        self.console = self.display.console

    async def get_input(self, prompt_text: str = "> ") -> str:
        """Get user input with visual effects.

        Args:
            prompt_text: Prompt text to display

        Returns:
            User input string
        """
        # For now, use simple prompt
        # TODO: Implement fancy input box with live updating
        return Prompt.ask(prompt_text)

    def display_user_message(self, content: str):
        """Display user message.

        Args:
            content: Message content
        """
        self.display.format_text_message(
            content,
            sender="You",
            border_style=self.display.BRAND_COLOR
        )
        self.console.print(self.display.format_text_message(content, "You"))

    def display_agent_message(self, content: str, agent_name: str = "Agent"):
        """Display agent message.

        Args:
            content: Message content
            agent_name: Agent name
        """
        self.console.print(self.display.format_text_message(content, agent_name))

    def display_tool_call(self, tool_call: dict):
        """Display tool call.

        Args:
            tool_call: Tool call event dict
        """
        tool_name = tool_call.get("tool_name", "unknown")
        args = tool_call.get("args", {})

        from rich.syntax import Syntax
        args_json = str(args)

        self.console.print(f"\n[dim]🔧 Calling {tool_name}...[/dim]")

    def display_tool_result(self, tool_result: dict):
        """Display tool result.

        Args:
            tool_result: Tool result event dict
        """
        tool_name = tool_result.get("tool_name", "unknown")
        status = tool_result.get("status", "unknown")

        if status == "success":
            self.console.print(f"[dim]✓ {tool_name} completed[/dim]")
        else:
            self.console.print(f"[red]✗ {tool_name} failed[/red]")

    def display_error(self, error: str):
        """Display error message.

        Args:
            error: Error message
        """
        self.console.print(f"[red]❌ Error: {error}[/red]")

    def clear(self):
        """Clear the console."""
        self.display.clear()

    def show_header(self):
        """Show application header."""
        self.display.show_header()

    def show_thinking(self, agent_name: str = "Agent"):
        """Show thinking indicator.

        Args:
            agent_name: Name of thinking agent

        Returns:
            ThinkingIndicator context manager
        """
        return self.display.show_thinking(agent_name)


class StreamingDisplay:
    """Handles streaming display of agent responses."""

    def __init__(self, prompt_interface: PromptInterface):
        """Initialize streaming display.

        Args:
            prompt_interface: PromptInterface instance
        """
        self.prompt = prompt_interface
        self.console = prompt_interface.console
        self.text_buffer = ""
        self.thinking_buffer = ""

    def on_text_delta(self, delta: str):
        """Handle text delta.

        Args:
            delta: Text delta
        """
        self.text_buffer += delta
        self.console.print(delta, end="", style=None)

    def on_thinking_delta(self, delta: str):
        """Handle thinking delta.

        Args:
            delta: Thinking delta
        """
        self.thinking_buffer += delta
        # For now, don't display thinking deltas (could show in special area)

    def on_tool_call(self, tool_call: dict):
        """Handle tool call.

        Args:
            tool_call: Tool call event dict
        """
        # Finish current text line
        if self.text_buffer:
            self.console.print()  # Newline
            self.text_buffer = ""

        self.prompt.display_tool_call(tool_call)

    def on_tool_result(self, tool_result: dict):
        """Handle tool result.

        Args:
            tool_result: Tool result event dict
        """
        self.prompt.display_tool_result(tool_result)

    def finish_text(self):
        """Finish displaying text (add newline)."""
        if self.text_buffer:
            self.console.print()  # Newline
            self.text_buffer = ""

    def finish_thinking(self):
        """Finish displaying thinking."""
        if self.thinking_buffer:
            # Could display summary or just clear
            self.thinking_buffer = ""
