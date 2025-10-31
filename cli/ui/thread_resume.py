"""Thread resume UI for CLI.

Handles displaying and selecting saved threads to resume.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from ..effects.display import Display


class ThreadResume:
    """Handles thread resume UI."""

    def __init__(self, display: Optional[Display] = None):
        """Initialize thread resume UI.

        Args:
            display: Display instance (creates one if not provided)
        """
        self.display = display or Display()
        self.console = self.display.console

    def format_relative_time(self, timestamp_str: str) -> str:
        """Format timestamp as relative time.

        Args:
            timestamp_str: ISO timestamp string

        Returns:
            Relative time string (e.g., "2 hours ago")
        """
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(dt.tzinfo)
            delta = now - dt

            if delta.total_seconds() < 60:
                return "just now"
            elif delta.total_seconds() < 3600:
                minutes = int(delta.total_seconds() / 60)
                return f"{minutes}m ago"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() / 3600)
                return f"{hours}h ago"
            elif delta.days < 7:
                return f"{delta.days}d ago"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"{weeks}w ago"
            else:
                return dt.strftime("%b %d")

        except Exception:
            return "unknown"

    def show_threads(self, threads: List[Dict[str, Any]]) -> Optional[str]:
        """Display thread list and get selection.

        Args:
            threads: List of thread metadata dicts

        Returns:
            Selected thread ID or None if cancelled
        """
        if not threads:
            self.console.print("[yellow]No saved conversations found.[/yellow]")
            return None

        # Create table
        table = Table(
            title="Saved Conversations",
            show_header=True,
            show_lines=True,
            expand=True
        )

        table.add_column("#", width=4, style="cyan", justify="right")
        table.add_column("Updated", width=12, style="dim")
        table.add_column("Messages", width=8, justify="right")
        table.add_column("Preview")

        # Add threads to table
        for idx, thread in enumerate(threads, 1):
            updated = self.format_relative_time(thread.get("updated_at", ""))
            message_count = thread.get("message_count", 0)
            preview = thread.get("preview", "No messages")

            # Truncate long previews
            if len(preview) > 70:
                preview = preview[:67] + "..."

            table.add_row(
                f"[{idx}]",
                updated,
                str(message_count),
                preview
            )

        self.console.print(table)
        self.console.print("\n[dim]Enter number to resume, 'q' to go back[/dim]")

        # Get selection
        while True:
            choice = Prompt.ask("Select conversation")

            if choice.lower() in ['q', 'quit', 'back', 'b']:
                return None

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(threads):
                    selected = threads[idx]
                    thread_id = selected.get("thread_id")
                    self.console.print(
                        f"\n[green]✓[/green] Resuming conversation..."
                    )
                    return thread_id
                else:
                    self.console.print("[red]Invalid selection. Try again.[/red]")
            except ValueError:
                self.console.print("[red]Please enter a number or 'q' to go back.[/red]")

    def show_thread_preview(self, events: List[Dict[str, Any]], limit: int = 5):
        """Show preview of thread events.

        Args:
            events: List of thread events
            limit: Number of recent events to show
        """
        self.console.print("\n[bold]Recent messages:[/bold]")

        # Find recent message events
        message_events = []
        for event in reversed(events):
            event_type = event.get("event_type")
            if event_type in ["user_message", "text"]:
                message_events.append(event)
                if len(message_events) >= limit:
                    break

        # Display in chronological order
        for event in reversed(message_events):
            event_type = event.get("event_type")
            content = event.get("content", "")

            if event_type == "user_message":
                sender = "You"
                style = "cyan"
            else:
                sender = "Agent"
                style = "green"

            # Truncate long messages
            if len(content) > 100:
                content = content[:97] + "..."

            self.console.print(f"  [{style}]{sender}:[/{style}] {content}")

        self.console.print()
