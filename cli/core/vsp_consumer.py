"""VSP SSE stream consumer for CLI.

Handles consuming VSP events from server SSE stream and processing them through
the ThreadProtocol builder.
"""

import json
import asyncio
from typing import AsyncIterator, Dict, Any, Optional, Callable
import httpx


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
        thread_jsonl: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete_event: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream chat response from server.

        Args:
            thread_jsonl: Complete ThreadProtocol JSONL to send
            on_event: Optional callback for each VSP event (for display)
            on_complete_event: Optional callback for complete ThreadProtocol events

        Yields:
            VSP event dicts
        """
        if not self.client:
            raise RuntimeError("Consumer not initialized. Use 'async with' context manager.")

        url = f"{self.base_url}/stream"

        # Send as POST with JSONL body
        async with self.client.stream(
            "POST",
            url,
            content=thread_jsonl,
            headers={
                "Content-Type": "application/x-jsonlines",
                "Accept": "text/event-stream"
            }
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
        thread_jsonl: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete_event: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Send user message and stream response.

        This is a convenience method that adds the user message event to the thread
        before streaming.

        Args:
            message: User message content
            thread_jsonl: Existing thread JSONL
            on_event: Optional callback for each VSP event
            on_complete_event: Optional callback for complete ThreadProtocol events

        Yields:
            VSP event dicts
        """
        from datetime import datetime, timezone

        # Build user turn events
        user_turn_start = {
            "event_type": "user_turn_start",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        user_message = {
            "event_type": "user_message",
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        user_turn_end = {
            "event_type": "user_turn_end",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Append to thread JSONL
        updated_jsonl = thread_jsonl + "\n" + "\n".join([
            json.dumps(user_turn_start),
            json.dumps(user_message),
            json.dumps(user_turn_end)
        ])

        # Stream response
        async for event in self.stream_chat(updated_jsonl, on_event, on_complete_event):
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

    async def process_stream(
        self,
        stream: AsyncIterator[Dict[str, Any]],
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_thinking_delta: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """Process VSP stream and update ThreadProtocol builder.

        Args:
            stream: AsyncIterator of VSP events
            on_text_delta: Callback for text deltas (for live display)
            on_thinking_delta: Callback for thinking deltas (for live display)
            on_tool_call: Callback for tool calls
            on_tool_result: Callback for tool results
        """
        async for vsp_event in stream:
            event_type = vsp_event.get("type")

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

            # Process through ThreadProtocol builder
            tp_event = self.builder.process_vsp_event(vsp_event)

            if tp_event:
                # Add to builder
                self.builder.add_event(tp_event)

                # Call specific callbacks
                if tp_event["event_type"] == "tool_call" and on_tool_call:
                    on_tool_call(tp_event)
                elif tp_event["event_type"] == "tool_result" and on_tool_result:
                    on_tool_result(tp_event)

        # Reset buffers for next turn
        self.text_buffer = ""
        self.thinking_buffer = ""


async def test_stream():
    """Simple test function for VSP consumer."""
    consumer = VSPStreamConsumer("http://localhost:8000")

    # Example blueprint event (would come from actual blueprint)
    blueprint = {
        "event_type": "thread_blueprint",
        "thread_id": "test-123",
        "timestamp": "2025-10-31T00:00:00Z",
        "blueprint_version": "0.0.1",
        "blueprint": {}
    }

    thread_jsonl = json.dumps(blueprint)

    from .thread_protocol import ThreadProtocolBuilder

    builder = ThreadProtocolBuilder(blueprint)
    processor = StreamProcessor(builder)

    async with consumer:
        try:
            stream = consumer.send_user_message(
                "Hello, how are you?",
                thread_jsonl
            )

            def on_text_delta(delta: str):
                print(delta, end="", flush=True)

            await processor.process_stream(
                stream,
                on_text_delta=on_text_delta
            )

            print("\n\nFinal JSONL:")
            print(builder.to_jsonl())

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_stream())
