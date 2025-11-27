"""
Blueprint Selection Screen.
"""

from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, OptionList


class BlueprintSelectScreen(ModalScreen[Dict[str, Any]]):
    """Screen for selecting a blueprint."""

    CSS = """
    BlueprintSelectScreen {
        align: center middle;
    }
    
    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }
    
    Label {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }
    
    OptionList {
        height: 1fr;
        border: solid $primary;
    }
    """

    def __init__(self, blueprints: List[Dict[str, Any]]):
        super().__init__()
        self.blueprints = blueprints

    def compose(self) -> ComposeResult:
        yield Label("Select a Blueprint to Start", id="title")

        # Create options from blueprints
        options = [
            f"{bp.get('name', 'Unknown')} ({bp.get('model', 'default')})" for bp in self.blueprints
        ]

        yield OptionList(*options, id="blueprint-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection."""
        selected_idx = event.option_index
        if selected_idx is not None and 0 <= selected_idx < len(self.blueprints):
            self.dismiss(self.blueprints[selected_idx])
        else:
            self.dismiss(None)
