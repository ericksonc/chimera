"""Streaming infrastructure for VSP and ThreadProtocol events.

This module provides the core streaming infrastructure that was previously
scattered in the API layer. It encapsulates:
- VSP event emission with proper threadId handling
- ThreadProtocol event persistence and VSP bridging
- Configurable logging for debugging

The API layer only needs to provide the asyncio.Queue (transport concern)
and pass the infrastructure's emit methods to ThreadDeps.

Architectural Principle:
- Core layer owns event generation and transformation
- API layer owns HTTP transport (queue consumption, SSE formatting)
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from chimera_core.threadprotocol.writer import ThreadProtocolWriter

logger = logging.getLogger(__name__)

# SSE Event logging - set to True to see all emitted events
VERBOSE_SSE_LOGGING = os.environ.get("CHIMERA_VERBOSE_SSE", "false").lower() == "true"


@dataclass
class StreamingInfrastructure:
    """Encapsulates streaming infrastructure for VSP and ThreadProtocol events.

    This class centralizes the emit function logic that was previously in
    api/stream_handler.py's factory functions (create_emit_vsp_event,
    create_emit_threadprotocol_event).

    The class handles:
    - VSP event emission with intelligent threadId injection
    - ThreadProtocol persistence and VSP bridging for mutations
    - Configurable logging for debugging

    Example:
        >>> queue = asyncio.Queue()
        >>> infrastructure = StreamingInfrastructure(
        ...     thread_id="thread_123",
        ...     event_queue=queue,
        ...     thread_writer=writer,
        ... )
        >>> deps = ThreadDeps(
        ...     emit_vsp_event=infrastructure.emit_vsp_event,
        ...     emit_threadprotocol_event=infrastructure.emit_threadprotocol_event,
        ...     thread_writer=writer,
        ... )
    """

    thread_id: str
    event_queue: asyncio.Queue
    thread_writer: Optional["ThreadProtocolWriter"] = None
    verbose_logging: bool = VERBOSE_SSE_LOGGING

    async def emit_vsp_event(self, event: dict, include_thread_id: bool = True) -> None:
        """Emit a VSP event to the streaming queue.

        This method handles threadId injection intelligently:
        - If include_thread_id=True and threadId not already in event, adds it
        - If include_thread_id=False, does not add threadId (for delta events)
        - If threadId already present (from VSPEventStream), preserves it

        Args:
            event: The VSP event dict to emit
            include_thread_id: Whether to add threadId to this event.
                              Default True for boundary events (start, turn boundaries, mutations).
                              Set to False for deltas (text-delta, tool-input-delta, reasoning-delta)
                              which reference by part ID instead.
        """
        # Add threadId if needed and not already present
        # This prevents duplicate injection when VSPEventStream already added it
        if include_thread_id and "threadId" not in event:
            event["threadId"] = self.thread_id

        # Log SSE events
        self._log_vsp_event(event)

        await self.event_queue.put(event)

    async def emit_threadprotocol_event(self, event: dict) -> None:
        """Write to ThreadProtocol AND emit as VSP if appropriate.

        This method:
        1. Writes the event to ThreadProtocol JSONL (persistence)
        2. For mutation events (data-app-chimera), also emits to VSP stream

        Some events go to both JSONL persistence and VSP streaming.
        Others (like internal state) might only go to JSONL.

        Args:
            event: The ThreadProtocol event dict to write
        """
        # Log ThreadProtocol events
        self._log_threadprotocol_event(event)

        # Write to ThreadProtocol (persistence)
        if self.thread_writer:
            await self.thread_writer.write_event(event)

        # Determine if this should also stream via VSP
        # State mutations (data-app-chimera) need to stream to client
        if event.get("type") == "data-app-chimera":
            # State mutations: include threadId (boundary event) - v0.0.7 nested structure
            # Events already in correct v0.0.7 format from emitters, just pass through
            vsp_event = {
                "type": "data-app-chimera",
                "data": event["data"],  # Already nested: {source, payload}
            }

            logger.info(f"[MUTATION] Streaming TP mutation as VSP: {vsp_event}")
            await self.emit_vsp_event(vsp_event, include_thread_id=True)

    def _log_vsp_event(self, event: dict) -> None:
        """Log VSP events with appropriate verbosity.

        Args:
            event: The VSP event to log
        """
        if self.verbose_logging:
            logger.info(f"[SSE EMIT] {json.dumps(event)}")
        elif event.get("type") not in ["text-delta", "tool-input-delta", "reasoning-delta"]:
            # Non-verbose: log everything except deltas
            # For errors, print the actual error message
            if event.get("type") == "error":
                logger.error(
                    f"[SSE EMIT] type=error thread={event.get('threadId', 'N/A')} "
                    f"error={event.get('errorText', 'N/A')}"
                )
            else:
                logger.info(
                    f"[SSE EMIT] type={event.get('type')} thread={event.get('threadId', 'N/A')}"
                )

    def _log_threadprotocol_event(self, event: dict) -> None:
        """Log ThreadProtocol events with appropriate verbosity.

        Args:
            event: The ThreadProtocol event to log
        """
        if self.verbose_logging:
            logger.info(f"[TP EMIT] {json.dumps(event)}")
        else:
            logger.info(f"[TP EMIT] type={event.get('type')}")


def create_streaming_infrastructure(
    thread_id: str,
    event_queue: asyncio.Queue,
    thread_writer: Optional["ThreadProtocolWriter"] = None,
) -> StreamingInfrastructure:
    """Factory function to create StreamingInfrastructure.

    This is the primary entry point for creating streaming infrastructure.
    The API layer creates the queue (transport concern) and passes it here.

    Args:
        thread_id: Thread ID to include in boundary events
        event_queue: asyncio.Queue for event transport
        thread_writer: ThreadProtocol writer for persistence (optional)

    Returns:
        Configured StreamingInfrastructure instance
    """
    return StreamingInfrastructure(
        thread_id=thread_id,
        event_queue=event_queue,
        thread_writer=thread_writer,
    )
