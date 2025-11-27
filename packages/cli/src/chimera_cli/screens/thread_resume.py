"""
Thread Resume Screen.
"""

from datetime import datetime
from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Label


class ThreadResumeScreen(ModalScreen[Dict[str, Any]]):
    """Screen for resuming a past thread."""

    CSS = """
    ThreadResumeScreen {
        align: center middle;
    }
    
    #dialog {
        width: 90%;
        height: 80%;
        border: thick $background 80%;
        background: $surface;
    }
    
    Label {
        width: 100%;
        content-align: center middle;
        margin: 1;
    }
    
    DataTable {
        height: 1fr;
        border: solid $primary;
    }
    """

    def __init__(self, threads: List[Dict[str, Any]]):
        super().__init__()
        self.threads = threads

    def compose(self) -> ComposeResult:
        yield Label("Select a Conversation to Resume", id="title")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Time", "Messages", "Preview")

        for idx, thread in enumerate(self.threads):
            # Format time
            try:
                created = datetime.fromisoformat(thread["created_at"])
                time_str = created.strftime("%Y-%m-%d %H:%M")
            except (ValueError, KeyError, TypeError):
                time_str = "Unknown"

            msg_count = str(thread.get("message_count", 0))
            preview = thread.get("preview", "")[:50] + "..."

            # Use index as row key
            table.add_row(time_str, msg_count, preview, key=str(idx))

        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle selection."""
        row_key = event.row_key.value
        try:
            idx = int(row_key)
            if 0 <= idx < len(self.threads):
                self.dismiss(self.threads[idx])
            else:
                self.dismiss(None)
        except ValueError:
            self.dismiss(None)
