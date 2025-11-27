#!/usr/bin/env python3
"""
Slash command system for cli_textual.

Provides fuzzy autocomplete suggestions for slash commands and command registry.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from textual.suggester import Suggester  # type: ignore


@dataclass
class SlashCommand:
    """Represents a slash command with shortcut and handler."""

    name: str  # Full command name (e.g., "blueprints")
    shortcut: str  # Shortcut letter (e.g., "b")
    description: str  # Help text for the command
    handler: Optional[Callable] = None  # Function to execute when command is invoked


class SlashCommandSuggester(Suggester):
    """Provides fuzzy autocomplete suggestions for slash commands."""

    def __init__(self, commands: Dict[str, SlashCommand]):
        super().__init__(case_sensitive=False)
        self.commands = commands

    async def get_suggestion(self, value: str) -> Optional[str]:
        """Return command suggestion based on input value."""
        if not value.startswith("/"):
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
    ),
    "/resume": SlashCommand(
        name="resume",
        shortcut="r",
        description="Resume a conversation",
    ),
    "/threads": SlashCommand(
        name="threads",
        shortcut="t",
        description="List all conversation threads",
    ),
    "/clear": SlashCommand(
        name="clear",
        shortcut="c",
        description="Clear current conversation",
    ),
    "/new": SlashCommand(
        name="new",
        shortcut="n",
        description="Start a new conversation",
    ),
    "/help": SlashCommand(
        name="help",
        shortcut="h",
        description="Show available commands",
    ),
    "/quit": SlashCommand(
        name="quit",
        shortcut="q",
        description="Quit the application",
    ),
    "/model": SlashCommand(
        name="model",
        shortcut="m",
        description="Select a model",
    ),
}
