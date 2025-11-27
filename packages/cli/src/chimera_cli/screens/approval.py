"""
Tool Approval Screen.
"""

import json
from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown


class ApprovalScreen(ModalScreen[Dict[str, Any]]):
    """Screen for approving tool calls."""

    CSS = """
    ApprovalScreen {
        align: center middle;
    }
    
    #dialog {
        width: 80%;
        height: 80%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    
    #title {
        text-align: center;
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    
    .tool-item {
        border: solid $primary;
        margin-bottom: 1;
        padding: 1;
        height: auto;
    }
    
    #buttons {
        height: 3;
        dock: bottom;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, pending_tools: List[Dict[str, Any]]):
        super().__init__()
        self.pending_tools = pending_tools

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("⚠ Tools Requiring Approval", id="title")

            with Vertical(id="tools-list"):
                for tool in self.pending_tools:
                    tool_name = tool.get("toolName", "unknown")
                    args = tool.get("input", {})
                    args_json = json.dumps(args, indent=2)

                    with Vertical(classes="tool-item"):
                        yield Label(f"Tool: {tool_name}", classes="tool-name")
                        yield Markdown(f"```json\n{args_json}\n```")

            with Horizontal(id="buttons"):
                yield Button("Approve All", variant="success", id="approve")
                yield Button("Reject All", variant="error", id="reject")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        approvals = {}

        # Determine approval status based on button ID
        is_approved = event.button.id == "approve"

        for tool in self.pending_tools:
            tool_call_id = tool.get("toolCallId")
            tool_name = tool.get("toolName", "unknown")

            if not tool_call_id:
                # Log error and notify user
                error_msg = f"Missing toolCallId for tool '{tool_name}'. Skipping."
                self.notify(error_msg, severity="error")
                continue

            if is_approved:
                approvals[tool_call_id] = True
            else:
                # Reject with generic message
                # TODO: Ask for rejection reason
                approvals[tool_call_id] = {"approved": False, "message": "Rejected by user"}

        self.dismiss(approvals)
