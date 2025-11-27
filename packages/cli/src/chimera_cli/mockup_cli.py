#!/usr/bin/env python3
"""
Mockup Textual CLI for Chimera v4

This is a mockup version that simulates AI responses without connecting to any backend.
The goal is to get the basic UI working: prompt box pinned to bottom, messages scrolling upward.
"""

import random
import time

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static


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


class AssistantMessage(Static):
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


class MockupCLI(App):
    """Mockup CLI with simulated AI responses."""

    AUTO_FOCUS = "Input"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }
    
    #chat-view {
        height: 1fr;
        background: $surface-darken-1;
    }
    
    Input {
        height: 3;
        background: $surface-lighten-1;
        border: tall $primary;
        margin: 0;
    }
    
    Input:focus {
        border: tall $accent;
    }
    """

    def __init__(self):
        super().__init__()
        self.chat_history = []

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        # Scrollable chat history
        with VerticalScroll(id="chat-view"):
            yield AssistantMessage(
                "Welcome to Chimera v4 Mockup CLI! Type a message below to start."
            )

        # Input for user messages (naturally sits at bottom)
        yield Input(placeholder="Ask me anything...")

    def on_mount(self) -> None:
        """Set up anchoring on mount."""
        chat_view = self.query_one("#chat-view", VerticalScroll)
        chat_view.anchor()  # Enable auto-scroll to bottom

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        """Handle when user submits input."""
        if not event.value.strip():
            return

        chat_view = self.query_one("#chat-view", VerticalScroll)
        user_text = event.value

        # Clear the input
        event.input.clear()

        # Add user's message to chat
        await chat_view.mount(UserMessage(f"**You:** {user_text}"))

        # Add response widget (will be updated as we stream)
        response_widget = AssistantMessage("")
        await chat_view.mount(response_widget)

        # Generate mock response in background
        self.generate_mock_response(user_text, response_widget)

    @work(thread=True)
    def generate_mock_response(self, user_prompt: str, response_widget: AssistantMessage) -> None:
        """Generate a mock AI response in a background thread."""

        # Simulate different response patterns based on input
        mock_responses = [
            "That's an interesting question! Let me think about it...",
            "I understand what you're asking. Based on my analysis...",
            "Great point! Here's what I think about that...",
            "Hmm, that's a complex topic. Let me break it down...",
            "I see what you mean. From my perspective...",
            "Excellent observation! This reminds me of...",
            "Let me consider that for a moment...",
            "That's a fascinating idea! Here's my take...",
        ]

        # Choose a base response
        base_response = random.choice(mock_responses)

        # Add some variation based on prompt length
        if len(user_prompt) > 50:
            base_response += (
                " This seems like a detailed query, so I'll provide a comprehensive answer."
            )

        # Simulate typing delay
        time.sleep(0.5)

        # Stream the response character by character
        full_response = f"**Assistant:** {base_response}"

        # Simulate streaming with varying speeds
        current_text = ""
        for i, char in enumerate(full_response):
            current_text += char

            # Vary the speed (faster for spaces, slower for punctuation)
            if char in ".!?":
                delay = 0.15
            elif char in ",;:":
                delay = 0.08
            elif char == " ":
                delay = 0.03
            else:
                delay = 0.02

            time.sleep(delay)

            # Update from thread (thread-safe)
            self.call_from_thread(response_widget.update, current_text)

        # Add a final thought
        time.sleep(0.3)
        final_addition = " Let me know if you'd like me to elaborate on any of these points!"
        full_response += final_addition

        # Stream the final addition
        for char in final_addition:
            current_text += char
            time.sleep(0.04)
            self.call_from_thread(response_widget.update, current_text)


if __name__ == "__main__":
    app = MockupCLI()
    app.run()
