"""VSP SSE stream consumer for CLI.

Handles consuming VSP events from server SSE stream and processing them through
the ThreadProtocol builder.
"""

import asyncio
import json
from typing import Any, AsyncIterator, Callable, Dict, Optional

import httpx

from chimera_core.types.user_input import UserInput, UserInputDeferredTools, UserInputMessage


class VSPStreamConsumer:
    """Consumes VSP SSE streams from server."""

    def __init__(self, base_url: str, timeout: float = 300.0):
        """Initialize consumer.

        Args:
            base_url: Base URL of the server (e.g., "http://localhost:8000")
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter context manager."""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self.client:
            await self.client.aclose()

    async def stream_chat(
        self,
        thread_protocol: list[Dict[str, Any]],
        user_input: str | UserInput,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream chat response from server.

        Args:
            thread_protocol: Array of ThreadProtocol event objects
            user_input: User input (str for convenience, or typed UserInput)
            on_event: Optional callback for each VSP event (for display)
            on_complete_event: Optional callback for complete ThreadProtocol events
            client_context: Optional client context dict (e.g. cwd)

        Yields:
            VSP event dicts
        """
        if not self.client:
            raise RuntimeError("Consumer not initialized. Use 'async with' context manager.")

        url = f"{self.base_url}/stream"

        # Convert string to UserInputMessage for convenience
        typed_input: UserInput
        if isinstance(user_input, str):
            typed_input = UserInputMessage(
                kind="message", content=user_input, client_context=client_context
            )
        else:
            typed_input = user_input
            # Inject client_context if provided and not already present
            if client_context and typed_input.client_context is None:
                typed_input.client_context = client_context

        # Build request payload (serialize Pydantic model to dict for JSON)
        request_payload = {
            "thread_protocol": thread_protocol,
            "user_input": typed_input.model_dump(),
        }

        # Send as POST with JSON body
        async with self.client.stream(
            "POST", url, json=request_payload, headers={"Accept": "text/event-stream"}
        ) as response:
            response.raise_for_status()

            # Process SSE stream
            async for line in response.aiter_lines():
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Handle SSE format: "data: {json}"
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix

                    # Check for stream completion signal
                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)

                        # Call display callback if provided
                        if on_event:
                            on_event(event)

                        yield event

                    except json.JSONDecodeError as e:
                        # Log but don't crash on bad JSON
                        print(f"Warning: Failed to parse SSE data: {e}")
                        continue

    async def send_user_message(
        self,
        message: str,
        thread_protocol: list[Dict[str, Any]],
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Send user message and stream response.

        This is a convenience wrapper around stream_chat.

        Args:
            message: User message content
            thread_protocol: Existing thread protocol events array
            on_event: Optional callback for each VSP event
            on_complete_event: Optional callback for complete ThreadProtocol events
            client_context: Optional client context dict (e.g. cwd)

        Yields:
            VSP event dicts
        """
        # Simply delegate to stream_chat with the new API format
        async for event in self.stream_chat(
            thread_protocol,
            message,
            on_event,
            on_complete_event,
            client_context=client_context,
        ):
            yield event

    async def send_deferred_approvals(
        self,
        approvals: Dict[str, Any],
        thread_protocol: list[Dict[str, Any]],
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Send deferred tool approvals and resume stream.

        Args:
            approvals: Dict mapping tool_call_id to approval decision
                      (bool or {"approved": False, "message": str})
            thread_protocol: Existing thread protocol events array
            on_event: Optional callback for each VSP event
            on_complete_event: Optional callback for complete ThreadProtocol events
            client_context: Optional client context dict (e.g. cwd)

        Yields:
            VSP event dicts
        """
        # Create typed UserInputDeferredTools object
        user_input = UserInputDeferredTools(
            kind="deferred_tools",
            approvals=approvals,
            calls={},  # External calls not yet supported in CLI
            client_context=client_context,
        )
        async for event in self.stream_chat(
            thread_protocol, user_input, on_event, on_complete_event
        ):
            yield event


class StreamProcessor:
    """Processes VSP stream through ThreadProtocol builder."""

    def __init__(self, thread_builder):
        """Initialize processor.

        Args:
            thread_builder: ThreadProtocolBuilder instance
        """
        self.builder = thread_builder
        self.text_buffer = ""  # Buffer for text display
        self.thinking_buffer = ""  # Buffer for thinking display
        self.approval_requests = []  # Track tool-approval-request events (v0.0.7)

    async def process_stream(
        self,
        stream: AsyncIterator[Dict[str, Any]],
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_thinking_delta: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_claude_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """Process VSP stream and update ThreadProtocol builder.

        Args:
            stream: AsyncIterator of VSP events
            on_text_delta: Callback for text deltas (for live display)
            on_thinking_delta: Callback for thinking deltas (for live display)
            on_tool_call: Callback for tool calls
            on_tool_result: Callback for tool results
            on_claude_event: Callback for Claude Code events (data-app-claude)
            on_error: Callback for error events (errorText: str)
        """
        # Reset approval requests at start of stream (v0.0.7)
        self.approval_requests = []

        async for vsp_event in stream:
            event_type = vsp_event.get("type")

            # Handle error events
            if event_type == "error":
                error_text = vsp_event.get("errorText", "Unknown error")
                if on_error:
                    on_error(error_text)
                # Stop processing stream after error
                break

            # Handle text deltas for live display
            if event_type == "text-delta" and on_text_delta:
                delta = vsp_event.get("delta", "")
                self.text_buffer += delta
                on_text_delta(delta)

            # Handle thinking deltas for live display
            elif event_type == "reasoning-delta" and on_thinking_delta:
                delta = vsp_event.get("delta", "")
                self.thinking_buffer += delta
                on_thinking_delta(delta)

            # Handle Claude Code events (v1.2 streaming)
            elif event_type == "data-app-claude" and on_claude_event:
                on_claude_event(vsp_event)

            # Track tool approval requests (v0.0.7 VSP v6 approach)
            elif event_type == "tool-approval-request":
                self.approval_requests.append(vsp_event)

            # Process through ThreadProtocol builder
            tp_event = self.builder.process_vsp_event(vsp_event)

            if tp_event:
                # Add to builder
                self.builder.add_event(tp_event)

                # Call specific callbacks
                if tp_event["type"] == "tool-input-available" and on_tool_call:
                    on_tool_call(tp_event)
                elif tp_event["type"] == "tool-output-available" and on_tool_result:
                    on_tool_result(tp_event)

        # Reset buffers for next turn
        self.text_buffer = ""
        self.thinking_buffer = ""

    def has_deferred_tools(self) -> bool:
        """Check if the last agent turn ended with deferred tools.

        v0.0.7: Detects deferred tools by presence of tool-approval-request events,
        not by completionStatus field (which was removed in v0.0.7).

        Returns:
            True if tools are awaiting approval
        """
        return len(self.approval_requests) > 0


async def test_stream():
    """Simple test function for VSP consumer."""
    consumer = VSPStreamConsumer("http://localhost:8000")

    # Example blueprint event (would come from actual blueprint)
    blueprint = {
        "type": "thread_blueprint",
        "thread_id": "test-123",
        "timestamp": "2025-10-31T00:00:00Z",
        "blueprint_version": "0.0.1",
        "blueprint": {},
    }

    # Thread protocol starts with just the blueprint
    thread_protocol = [blueprint]

    from chimera_cli.core.thread_protocol import ThreadProtocolBuilder

    builder = ThreadProtocolBuilder(blueprint)
    processor = StreamProcessor(builder)

    async with consumer:
        try:
            stream = consumer.send_user_message("Hello, how are you?", thread_protocol)

            def on_text_delta(delta: str):
                print(delta, end="", flush=True)

            await processor.process_stream(stream, on_text_delta=on_text_delta)

            print("\n\nFinal JSONL:")
            print(builder.to_jsonl())

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_stream())
