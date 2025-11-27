"""
Model Selection Screen.
"""

from typing import Any, Dict, List, Optional

from textual.app import ComposeResult  # type: ignore
from textual.screen import ModalScreen  # type: ignore
from textual.widgets import Footer, Label, OptionList  # type: ignore


class ModelSelectScreen(ModalScreen[Optional[str]]):
    """Screen for selecting a model."""

    CSS = """
    ModelSelectScreen {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 1;
        width: 80;
        height: 20;
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

    def __init__(self, models: List[Dict[str, Any]]):
        super().__init__()
        self.models = models

    def compose(self) -> ComposeResult:
        yield Label("Select a Model", id="title")

        # Create options from models with pricing info
        options = []
        for model in self.models:
            display_name = model.get("display_name", model.get("id", "Unknown"))
            provider = model.get("provider", "").upper()

            # Format pricing
            pricing = model.get("pricing")
            if pricing:
                input_cost = pricing.get("input_cost_per_million", 0)
                output_cost = pricing.get("output_cost_per_million", 0)
                price_str = f"${input_cost:.2f}/${output_cost:.2f}"
            else:
                price_str = "free"

            options.append(f"{provider}: {display_name} ({price_str})")

        yield OptionList(*options, id="model-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection."""
        selected_idx = event.option_index
        if selected_idx is not None and 0 <= selected_idx < len(self.models):
            # Return the model ID
            self.dismiss(self.models[selected_idx].get("id"))
        else:
            self.dismiss(None)
