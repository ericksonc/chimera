"""ThreadProtocol Writer - Writes events to JSONL files.

This handles persisting ThreadProtocol events to JSONL files.
Each event is one line, written immediately and flushed.
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any
from contextlib import asynccontextmanager


class ThreadProtocolWriter:
    """Writes events to ThreadProtocol JSONL file.

    Usage:
        async with ThreadProtocolWriter("thread-123.jsonl") as writer:
            await writer.write_event({
                "event_type": "user_message",
                "content": "Hello!"
            })
    """

    def __init__(self, file_path: str | Path):
        """Initialize writer with file path.

        Args:
            file_path: Path to JSONL file (will be created/appended to)
        """
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> 'ThreadProtocolWriter':
        """Open file for appending."""
        self._file = open(self.file_path, 'a', encoding='utf-8')
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

    async def write_event(self, event: dict) -> None:
        """Write a single event to the JSONL file.

        Automatically adds timestamp if not present.

        Args:
            event: Event dictionary to write
        """
        if not self._file:
            raise RuntimeError("Writer not open. Use 'async with' context manager.")

        async with self._lock:
            # Add timestamp if not present
            if 'timestamp' not in event:
                event['timestamp'] = datetime.now(timezone.utc).isoformat()

            # Write as single line
            line = json.dumps(event, ensure_ascii=False) + '\n'
            self._file.write(line)
            self._file.flush()  # Immediate flush for durability

    async def write_blueprint(
        self,
        thread_id: str,
        blueprint: dict,
        blueprint_version: str = "0.0.1"
    ) -> None:
        """Write the blueprint event (must be first line).

        Args:
            thread_id: UUID of the thread
            blueprint: Blueprint configuration dict
            blueprint_version: Version of blueprint protocol
        """
        event = {
            "event_type": "thread_blueprint",
            "thread_id": thread_id,
            "blueprint_version": blueprint_version,
            "blueprint": blueprint
        }
        await self.write_event(event)

    async def write_user_message(self, content: str, **metadata) -> None:
        """Convenience method to write user message event.

        Args:
            content: Message content
            **metadata: Additional metadata fields
        """
        event = {
            "event_type": "user_message",
            "content": content,
            **metadata
        }
        await self.write_event(event)

    async def write_text_response(
        self,
        content: str,
        agent_id: str,
        **metadata
    ) -> None:
        """Convenience method to write agent text response.

        Args:
            content: Response text
            agent_id: UUID of responding agent
            **metadata: Additional metadata fields
        """
        event = {
            "event_type": "text",
            "content": content,
            "agent_id": agent_id,
            **metadata
        }
        await self.write_event(event)

    async def write_tool_call(
        self,
        tool_name: str,
        args: dict,
        tool_call_id: str,
        agent_id: str,
        **metadata
    ) -> None:
        """Write tool call event.

        Args:
            tool_name: Name of tool being called
            args: Tool arguments
            tool_call_id: Unique ID for this tool call
            agent_id: UUID of agent making the call
            **metadata: Additional metadata fields
        """
        event = {
            "event_type": "tool_call",
            "tool_name": tool_name,
            "args": args,
            "tool_call_id": tool_call_id,
            "agent_id": agent_id,
            **metadata
        }
        await self.write_event(event)

    async def write_tool_result(
        self,
        status: str,
        result: Any,
        tool_name: str,
        tool_call_id: str,
        **metadata
    ) -> None:
        """Write tool result event.

        Args:
            status: "success" or "error"
            result: Tool return value or error message
            tool_name: Name of tool that was called
            tool_call_id: ID of the tool call this is responding to
            **metadata: Additional metadata fields
        """
        event = {
            "event_type": "tool_result",
            "status": status,
            "result": result,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            **metadata
        }
        await self.write_event(event)

    async def write_turn_boundary(
        self,
        boundary_type: str,
        **metadata
    ) -> None:
        """Write turn boundary event.

        Args:
            boundary_type: Event type (e.g., "user_turn_start", "agent_turn_end")
            **metadata: Additional metadata fields
        """
        event = {
            "event_type": boundary_type,
            **metadata
        }
        await self.write_event(event)