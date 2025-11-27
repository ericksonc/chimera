import json
from typing import Any

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Markdown, Static


class UserMessage(Static):
    """Widget for displaying user messages."""

    DEFAULT_CSS = """
    UserMessage {
        background: $primary 15%;
        color: $text;
        margin: 1;
        margin-right: 8;
        padding: 1 2;
        height: auto;
        border-left: heavy $primary;
    }
    """


class AssistantMessage(Markdown):
    """Widget for displaying assistant messages."""

    DEFAULT_CSS = """
    AssistantMessage {
        background: $success 10%;
        color: $text;
        margin: 1;
        margin-left: 8;
        padding: 1 2;
        height: auto;
        border-left: heavy $success;
    }
    """


class ThinkingMessage(Static):
    """Widget for displaying reasoning/thinking content."""

    DEFAULT_CSS = """
    ThinkingMessage {
        background: $surface-lighten-1;
        color: $text-muted;
        margin: 1;
        margin-left: 8;
        padding: 1 2;
        height: auto;
        border-left: heavy $warning;
        text-style: italic;
    }
    """

    def __init__(self, text: str = ""):
        super().__init__(text)
        self.text_buffer = text

    def update_text(self, delta: str):
        self.text_buffer += delta
        self.update(self.text_buffer)


class ToolCallMessage(Static):
    """Widget for displaying tool calls."""

    DEFAULT_CSS = """
    ToolCallMessage {
        background: $accent 10%;
        color: $text;
        margin: 1;
        margin-left: 8;
        padding: 1 2;
        height: auto;
        border-left: heavy $accent;
    }
    """

    def __init__(self, tool_name: str, tool_input: Any):
        super().__init__("")
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.update_content()

    def update_content(self):
        # Handle input being string (already JSON) or dict
        if isinstance(self.tool_input, str):
            try:
                # Try to parse to ensure it's valid JSON for formatting
                parsed = json.loads(self.tool_input)
                input_json = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                input_json = self.tool_input
        else:
            input_json = json.dumps(self.tool_input, indent=2)

        header = Text.assemble(
            ("🛠️  Tool Call: ", "bold magenta"), (self.tool_name, "bold cyan"), "\n"
        )

        self.update(Group(header, Syntax(input_json, "json", theme="monokai")))


class ToolResultMessage(Static):
    """Widget for displaying tool results."""

    DEFAULT_CSS = """
    ToolResultMessage {
        background: $accent 5%;
        color: $text;
        margin: 1;
        margin-left: 8;
        padding: 1 2;
        height: auto;
        border-left: heavy $accent;
        opacity: 0.8;
    }
    .error {
        border-left: heavy $error;
        background: $error 10%;
    }
    """

    def __init__(self, tool_name: str, output: Any, status: str = "success"):
        super().__init__("")
        self.tool_name = tool_name
        self.output = output
        self.status = status
        if status != "success":
            self.add_class("error")
        self.update_content()

    def update_content(self):
        renderable = None
        label_suffix = ""

        if isinstance(self.output, (dict, list)):
            result_str = json.dumps(self.output, indent=2)
            lines = result_str.split("\n")

            if len(lines) > 3:
                preview = "\n".join(lines[:3])
                preview += f"\n... ({len(lines) - 3} more lines)"
                renderable = Syntax(preview, "json", theme="monokai")
                label_suffix = " (truncated)"
            else:
                renderable = Syntax(result_str, "json", theme="monokai")

        elif isinstance(self.output, str):
            if len(self.output) > 100:
                lines = self.output.split("\n")
                if len(lines) > 3:
                    preview = "\n".join(lines[:3])
                    preview += f"\n... ({len(lines) - 3} more lines, {len(self.output):,} chars)"
                    renderable = Text(preview)
                elif len(self.output) > 200:
                    preview = self.output[:200] + f"... ({len(self.output):,} chars)"
                    renderable = Text(preview)
                else:
                    renderable = Text(self.output)

                if renderable.plain != self.output:
                    label_suffix = " (truncated)"
            else:
                renderable = Text(self.output)
        else:
            renderable = Text(str(self.output))

        if self.status == "success":
            icon = "✅"
            style = "bold green"
            label = "Tool Result"
        else:
            icon = "❌"
            style = "bold red"
            label = "Tool Failed"

        content = Text.assemble(
            (f"{icon} {label}{label_suffix}: ", style),
            (self.tool_name, "bold cyan"),
            "\n",
        )

        self.update(Group(content, renderable))
