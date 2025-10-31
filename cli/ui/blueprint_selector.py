"""Blueprint selection UI for CLI.

Handles displaying and selecting blueprints.
"""

from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel

from ..effects.display import Display


class BlueprintSelector:
    """Handles blueprint selection UI."""

    def __init__(self, display: Optional[Display] = None):
        """Initialize blueprint selector.

        Args:
            display: Display instance (creates one if not provided)
        """
        self.display = display or Display()
        self.console = self.display.console

    def show_blueprints(self, blueprints: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Display blueprint list and get selection.

        Args:
            blueprints: List of blueprint metadata dicts

        Returns:
            Selected blueprint data dict or None if cancelled
        """
        if not blueprints:
            self.console.print("[yellow]No blueprints found.[/yellow]")
            return None

        # Create table
        table = Table(
            title="Available Blueprints",
            show_header=True,
            show_lines=True,
            expand=True
        )

        table.add_column("#", width=4, style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Version", width=10, style="dim")
        table.add_column("Description")

        # Add blueprints to table
        for idx, blueprint in enumerate(blueprints, 1):
            name = blueprint.get("name", "Unknown")
            version = blueprint.get("blueprint_version", "unknown")
            description = blueprint.get("description", "No description")

            # Truncate long descriptions
            if len(description) > 60:
                description = description[:57] + "..."

            table.add_row(
                f"[{idx}]",
                name,
                version,
                description
            )

        self.console.print(table)
        self.console.print("\n[dim]Enter number to select, 'q' to quit[/dim]")

        # Get selection
        while True:
            choice = Prompt.ask("Select blueprint")

            if choice.lower() in ['q', 'quit', 'exit']:
                return None

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(blueprints):
                    selected = blueprints[idx]
                    self.console.print(
                        f"\n[green]✓[/green] Selected: {selected.get('name', 'Unknown')}"
                    )
                    return selected["blueprint_data"]
                else:
                    self.console.print("[red]Invalid selection. Try again.[/red]")
            except ValueError:
                self.console.print("[red]Please enter a number or 'q' to quit.[/red]")

    def show_blueprint_info(self, blueprint_data: Dict[str, Any]):
        """Display detailed blueprint information.

        Args:
            blueprint_data: Blueprint data dict
        """
        blueprint = blueprint_data.get("blueprint", {})

        # Extract info
        agents = blueprint.get("agents", [])
        space = blueprint.get("space", {})

        info_text = []

        # Space info
        space_class = space.get("class_name", "Unknown")
        info_text.append(f"[bold]Space:[/bold] {space_class}")

        # Agents info
        info_text.append(f"\n[bold]Agents:[/bold]")
        for agent in agents:
            agent_name = agent.get("name", "Unknown")
            agent_desc = agent.get("description", "No description")
            info_text.append(f"  • {agent_name}: {agent_desc}")

        # Widgets
        widgets = []
        for agent in agents:
            agent_widgets = agent.get("widgets", [])
            widgets.extend(agent_widgets)

        if widgets:
            info_text.append(f"\n[bold]Widgets:[/bold]")
            for widget in widgets:
                widget_class = widget.get("class_name", "Unknown")
                info_text.append(f"  • {widget_class}")

        self.console.print(Panel(
            "\n".join(info_text),
            title="Blueprint Details",
            border_style=self.display.BRAND_COLOR,
            padding=(1, 2)
        ))
