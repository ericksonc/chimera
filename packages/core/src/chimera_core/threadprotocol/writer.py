"""ThreadProtocol Writer - Writes events to JSONL files.

This handles persisting ThreadProtocol events to JSONL files.
Each event is one line, written immediately and flushed.

v0.0.7: ThreadProtocol IS condensed VSP. The ONLY difference is delta
condensation - everything else passes through unchanged (camelCase, hyphens).
Uses EventCondenser to transform streaming events into condensed JSONL events.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chimera_core.threadprotocol.condensation import EventCondenser


class ThreadProtocolWriter:
    """Writes events to ThreadProtocol JSONL file.

    v0.0.7: Uses EventCondenser to transform VSP streaming events into
    condensed JSONL events. Deltas are accumulated, terminal events trigger
    writing complete events.

    Usage:
        async with ThreadProtocolWriter("thread-123.jsonl") as writer:
            # Streams deltas, writes condensed
            await writer.write_event({"type": "text-start", "id": "txt-1"})
            await writer.write_event({"type": "text-delta", "id": "txt-1", "delta": "Hi"})
            await writer.write_event({"type": "text-end", "id": "txt-1"})
            # Only text-complete is written to JSONL
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
        self._condenser = EventCondenser()  # Accumulates deltas

    async def __aenter__(self) -> "ThreadProtocolWriter":
        """Open file for appending."""
        self._file = open(self.file_path, "a", encoding="utf-8")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close file."""
        if self._file:
            self._file.close()
            self._file = None

    async def write_event(self, event: dict) -> None:
        """Write a VSP event to the JSONL file (with condensation).

        This processes the event through the condenser. Only complete events
        (text-complete, reasoning-complete, etc.) are written to JSONL.
        Intermediate deltas are accumulated but not persisted.

        Automatically adds timestamp if not present.

        Args:
            event: VSP event dictionary
        """
        if not self._file:
            raise RuntimeError("Writer not open. Use 'async with' context manager.")

        # Process through condenser
        condensed_event = self._condenser.process_event(event)

        # Only write if condenser returned a complete event
        if condensed_event is not None:
            async with self._lock:
                # Add timestamp if not present
                if "timestamp" not in condensed_event:
                    condensed_event["timestamp"] = datetime.now(timezone.utc).isoformat()

                # Write as single line
                line = json.dumps(condensed_event, ensure_ascii=False) + "\n"
                self._file.write(line)
                self._file.flush()  # Immediate flush for durability

    async def write_blueprint(
        self, thread_id: str, blueprint: dict, blueprint_version: str = "0.0.7"
    ) -> None:
        """Write the blueprint event (must be first line).

        Blueprints bypass condensation and are written directly.

        Args:
            thread_id: UUID of the thread
            blueprint: Blueprint configuration dict
            blueprint_version: Version of blueprint protocol (v0.0.7)
        """
        if not self._file:
            raise RuntimeError("Writer not open. Use 'async with' context manager.")

        event = {
            "type": "thread-blueprint",
            "threadId": thread_id,
            "blueprintVersion": blueprint_version,
            "blueprint": blueprint,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Write directly (blueprints bypass condensation)
        async with self._lock:
            line = json.dumps(event, ensure_ascii=False) + "\n"
            self._file.write(line)
            self._file.flush()

    async def write_user_message(self, content: str, **metadata) -> None:
        """Convenience method to write user message event (VSP format).

        Args:
            content: Message content
            **metadata: Additional metadata fields (camelCase)
        """
        event = {"type": "user-message", "content": content, **metadata}
        await self.write_event(event)

    async def write_text_response(self, content: str, agent_id: str, **metadata) -> None:
        """Convenience method to write agent text response (VSP format).

        Args:
            content: Response text
            agent_id: UUID of responding agent
            **metadata: Additional metadata fields (camelCase)
        """
        event = {"type": "text", "content": content, "agentId": agent_id, **metadata}
        await self.write_event(event)

    async def write_tool_call(
        self, tool_name: str, args: dict, tool_call_id: str, agent_id: str, **metadata
    ) -> None:
        """Write tool call event (VSP format).

        Args:
            tool_name: Name of tool being called
            args: Tool arguments
            tool_call_id: Unique ID for this tool call
            agent_id: UUID of agent making the call
            **metadata: Additional metadata fields (camelCase)
        """
        event = {
            "type": "tool-input-available",
            "toolName": tool_name,
            "input": args,
            "toolCallId": tool_call_id,
            "agentId": agent_id,
            **metadata,
        }
        await self.write_event(event)

    async def write_tool_result(
        self, status: str, result: Any, tool_name: str, tool_call_id: str, **metadata
    ) -> None:
        """Write tool result event (VSP format).

        Args:
            status: "success" or "error"
            result: Tool return value or error message
            tool_name: Name of tool that was called
            tool_call_id: ID of the tool call this is responding to
            **metadata: Additional metadata fields (camelCase)
        """
        event = {
            "type": "tool-output-available",
            "output": result,
            "toolName": tool_name,
            "toolCallId": tool_call_id,
            **metadata,
        }
        await self.write_event(event)

    async def write_turn_boundary(self, boundary_type: str, **metadata) -> None:
        """Write turn boundary event.

        v0.0.7: Multi-agent boundaries use data-agent-start/finish.
        These pass through condensation unchanged.

        Args:
            boundary_type: Event type (e.g., "data-agent-start", "data-agent-finish")
            **metadata: Additional metadata fields (camelCase)
        """
        event = {"type": boundary_type, **metadata}
        await self.write_event(event)

    def reset_condensers(self) -> None:
        """Reset all accumulators (e.g., between messages).

        Useful when starting a new message to clear any incomplete state.
        """
        self._condenser.reset()


class NoOpThreadProtocolWriter:
    """No-op writer for testing and scenarios where persistence isn't needed.

    This provides the same interface as ThreadProtocolWriter but doesn't
    write anything to disk. Useful for:
    - Unit tests that don't need persistence
    - Streaming-only scenarios where client handles persistence
    - Development/debugging

    Usage:
        async with NoOpThreadProtocolWriter() as writer:
            await writer.write_event({"type": "text", "content": "Hi"})
            # Nothing is persisted
    """

    async def __aenter__(self) -> "NoOpThreadProtocolWriter":
        """No-op context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """No-op context manager exit."""
        pass

    async def write_event(self, event: dict) -> None:
        """No-op write - discards the event."""
        pass

    async def write_blueprint(
        self, thread_id: str, blueprint: dict, blueprint_version: str = "0.0.7"
    ) -> None:
        """No-op blueprint write."""
        pass

    async def write_user_message(self, content: str, **metadata) -> None:
        """No-op user message write."""
        pass

    async def write_text_response(self, content: str, agent_id: str, **metadata) -> None:
        """No-op text response write."""
        pass

    async def write_tool_call(
        self, tool_name: str, args: dict, tool_call_id: str, agent_id: str, **metadata
    ) -> None:
        """No-op tool call write."""
        pass

    async def write_tool_result(
        self, status: str, result: Any, tool_name: str, tool_call_id: str, **metadata
    ) -> None:
        """No-op tool result write."""
        pass

    async def write_turn_boundary(self, boundary_type: str, **metadata) -> None:
        """No-op turn boundary write."""
        pass

    def reset_condensers(self) -> None:
        """No-op reset."""
        pass
