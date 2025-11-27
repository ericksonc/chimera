"""ThreadProtocol persistence wrapper for UI event streams.

This module provides a wrapper that adds ThreadProtocol JSONL persistence
to any UIEventStream without coupling the stream to persistence logic.

This maintains separation of concerns:
- UIEventStream: Pure event transformation (VSP, AG-UI, etc.)
- ThreadProtocolPersistenceWrapper: Storage concern (JSONL persistence)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, Optional

from .event_stream import UIEventStream

# Type alias for emit function
EmitFunc = Callable[[dict], Awaitable[None]]


@dataclass
class ThreadProtocolPersistenceWrapper:
    """Wraps any UIEventStream to add ThreadProtocol persistence.

    This wrapper intercepts important events and writes them to ThreadProtocol
    JSONL while passing through all events unchanged to the wrapped stream.

    Only events that need persistence are written to ThreadProtocol:
    - start, finish (message boundaries)
    - tool-input-available, tool-output-available (tool execution)
    - tool-approval-request, tool-output-denied (tool approval)

    Streaming deltas (text-delta, reasoning-delta) only go to the wrapped stream.

    Example:
        >>> vsp_stream = VSPEventStream(message_id="msg_123")
        >>> persisted_stream = ThreadProtocolPersistenceWrapper(
        ...     wrapped_stream=vsp_stream,
        ...     emit_threadprotocol=emit_tp_func
        ... )
        >>> async for event in persisted_stream.transform_pai_stream(agent_run):
        ...     # Event emitted to client
        ...     # Important events also persisted to ThreadProtocol
    """

    wrapped_stream: UIEventStream
    emit_threadprotocol: EmitFunc

    async def transform_pai_stream(
        self, pai_agent_run, on_complete: Optional[Callable] = None
    ) -> AsyncIterator[dict]:
        """Transform PAI stream with ThreadProtocol persistence.

        Wraps the underlying stream's transform_pai_stream() method,
        intercepting events to persist them to ThreadProtocol.

        Args:
            pai_agent_run: The async context manager from pai_agent.iter()
            on_complete: Optional callback when stream completes

        Yields:
            UI protocol events (dicts) from wrapped stream
        """
        async for event in self.wrapped_stream.transform_pai_stream(pai_agent_run, on_complete):
            # Skip transient events (ephemeral UI events like data-app-claude)
            if event.get("transient"):
                yield event
                continue

            # Persist important events to ThreadProtocol
            event_type = event.get("type")

            if event_type == "start":
                # Message boundary
                await self.emit_threadprotocol({"type": "start", "messageId": event["messageId"]})

            elif event_type == "finish":
                # Message boundary
                await self.emit_threadprotocol(
                    {"type": "finish", "messageId": event.get("messageId", "")}
                )

            elif event_type == "tool-input-available":
                # Tool execution - persist with timestamp
                await self.emit_threadprotocol(
                    {
                        "type": "tool-input-available",
                        "toolCallId": event["toolCallId"],
                        "toolName": event["toolName"],
                        "input": event["input"],
                        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    }
                )

            elif event_type == "tool-output-available":
                # Tool result - persist with timestamp
                await self.emit_threadprotocol(
                    {
                        "type": "tool-output-available",
                        "toolCallId": event["toolCallId"],
                        "toolName": event["toolName"],
                        "output": event["output"],
                        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    }
                )

            elif event_type == "tool-approval-request":
                # Tool approval - persist
                await self.emit_threadprotocol(
                    {
                        "type": "tool-approval-request",
                        "approvalId": event["approvalId"],
                        "toolCallId": event["toolCallId"],
                    }
                )

            elif event_type == "tool-output-denied":
                # Tool denial - persist
                await self.emit_threadprotocol(
                    {"type": "tool-output-denied", "toolCallId": event["toolCallId"]}
                )

            # Always yield event to client (stream-through)
            yield event


async def emit_tool_output_denied(
    tool_call_id: str,
    emit_threadprotocol: Optional[EmitFunc] = None,
    emit_vsp: Optional[EmitFunc] = None,
):
    """Helper to emit tool-output-denied events.

    This is called outside the stream when processing deferred tool denials.

    Args:
        tool_call_id: The tool call ID that was denied
        emit_threadprotocol: Optional ThreadProtocol emitter
        emit_vsp: Optional VSP emitter
    """
    event = {"type": "tool-output-denied", "toolCallId": tool_call_id}

    if emit_threadprotocol:
        await emit_threadprotocol(event)

    if emit_vsp:
        await emit_vsp(event)


async def emit_tool_approval_request(
    approval_id: str,
    tool_call_id: str,
    emit_threadprotocol: Optional[EmitFunc] = None,
    emit_vsp: Optional[EmitFunc] = None,
):
    """Helper to emit tool-approval-request events.

    This is called after the stream when DeferredToolRequests are detected.

    Args:
        approval_id: Unique approval request ID
        tool_call_id: The tool call ID needing approval
        emit_threadprotocol: Optional ThreadProtocol emitter
        emit_vsp: Optional VSP emitter
    """
    event = {"type": "tool-approval-request", "approvalId": approval_id, "toolCallId": tool_call_id}

    if emit_threadprotocol:
        await emit_threadprotocol(event)

    if emit_vsp:
        await emit_vsp(event)
