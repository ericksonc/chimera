"""Vercel AI SDK Data Stream Protocol (VSP) event stream implementation.

This module provides VSP-specific event transformation using the hook-based
UIEventStream pattern.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

from .event_stream import UIEventStream

logger = logging.getLogger(__name__)


@dataclass
class VSPEventStream(UIEventStream):
    """Vercel AI SDK Data Stream Protocol event transformer.

    This class transforms Pydantic AI events into VSP-compatible events
    for streaming to Vercel AI SDK clients.

    VSP Event Types:
        - start, finish, done - Message boundaries
        - text-start, text-delta, text-end - Text streaming
        - reasoning-start, reasoning-delta, reasoning-end - Thinking/reasoning
        - tool-input-start, tool-input-delta, tool-input-available - Tool calls
        - tool-output-available, tool-output-denied, tool-output-error - Tool results
        - start-step, finish-step - Model request boundaries

    Example:
        >>> stream = VSPEventStream(message_id="msg_123", thread_id="thread_456")
        >>> async for event in stream.transform_pai_stream(agent_run):
        ...     print(event)  # {"type": "text-delta", "id": "msg_123_text_0", "delta": "Hello"}
    """

    thread_id: str = ""  # Optional thread ID for boundary events
    include_thread_id: bool = True  # Whether to include threadId in boundary events

    # ==================== STREAM-LEVEL HOOKS ====================

    async def before_stream(self) -> AsyncIterator[dict]:
        """Emit start event at beginning of message."""
        yield {"type": "start", "messageId": self.message_id}

    async def after_stream(self) -> AsyncIterator[dict]:
        """Emit finish event at end of message.

        Note: [DONE] sentinel is handled separately by stream_handler.py
        via None queue sentinel, not as a JSON event.
        """
        yield {"type": "finish", "messageId": self.message_id}

    async def on_error(self, error: Exception) -> AsyncIterator[dict]:
        """Emit error event if stream fails."""
        logger.error(f"VSP stream error: {error}")
        yield {"type": "error", "errorText": str(error)}

    # ==================== TURN-LEVEL HOOKS ====================

    async def before_request(self) -> AsyncIterator[dict]:
        """Emit start-step when entering tool execution phase."""
        # VSP v6: start-step marks beginning of tool execution
        yield {"type": "start-step"}

    async def after_response(self) -> AsyncIterator[dict]:
        """Emit finish-step when model response completes."""
        # VSP v6: finish-step marks end of model processing
        yield {"type": "finish-step"}

    # ==================== TEXT PART HOOKS ====================

    async def handle_text_start(self, part: TextPart, index: int) -> AsyncIterator[dict]:
        """Emit text-start event and register part."""
        part_id = f"{self.message_id}_text_{index}"
        self._active_parts[index] = {"id": part_id, "type": "text"}

        # Emit text-start (boundary event)
        event = {"type": "text-start", "id": part_id}
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id
        yield event

        # If initial content exists, emit it as delta
        if part.content:
            yield {"type": "text-delta", "id": part_id, "delta": part.content}

    async def handle_text_delta(self, delta: TextPartDelta, part_info: dict) -> AsyncIterator[dict]:
        """Emit text-delta event."""
        if delta.content_delta:
            yield {"type": "text-delta", "id": part_info["id"], "delta": delta.content_delta}

    async def handle_text_end(self, part_info: dict) -> AsyncIterator[dict]:
        """Emit text-end event."""
        event = {"type": "text-end", "id": part_info["id"]}
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id
        yield event

    # ==================== TOOL CALL PART HOOKS ====================

    async def handle_tool_call_start(self, part: ToolCallPart, index: int) -> AsyncIterator[dict]:
        """Emit tool-input-start event and register part."""
        tool_call_id = part.tool_call_id or f"call_{uuid4().hex}"
        self._active_parts[index] = {"id": tool_call_id, "type": "tool", "name": part.tool_name}

        # Emit tool-input-start (boundary event)
        event = {"type": "tool-input-start", "toolCallId": tool_call_id, "toolName": part.tool_name}
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id
        yield event

    async def handle_tool_call_delta(
        self, delta: ToolCallPartDelta, part_info: dict
    ) -> AsyncIterator[dict]:
        """Emit tool-input-delta event."""
        if delta.args_delta:
            args_str = (
                delta.args_delta if isinstance(delta.args_delta, str) else str(delta.args_delta)
            )
            yield {
                "type": "tool-input-delta",
                "toolCallId": part_info["id"],
                "inputTextDelta": args_str,
            }

    async def handle_tool_call_available(self, event: FunctionToolCallEvent) -> AsyncIterator[dict]:
        """Emit tool-input-available event when tool is about to execute."""
        tool_call_id = event.part.tool_call_id or f"call_{uuid4().hex}"

        vsp_event = {
            "type": "tool-input-available",
            "toolCallId": tool_call_id,
            "toolName": event.part.tool_name,
            "input": event.part.args,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.include_thread_id and self.thread_id:
            vsp_event["threadId"] = self.thread_id

        yield vsp_event

    async def handle_tool_result(self, event: FunctionToolResultEvent) -> AsyncIterator[dict]:
        """Emit tool-output-available event when tool execution completes."""
        tool_call_id = (
            event.result.tool_call_id
            if hasattr(event.result, "tool_call_id")
            else f"call_{uuid4().hex}"
        )

        vsp_event = {
            "type": "tool-output-available",
            "toolCallId": tool_call_id,
            "toolName": event.result.tool_name,
            "output": event.result.content
            if hasattr(event.result, "content")
            else str(event.result),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.include_thread_id and self.thread_id:
            vsp_event["threadId"] = self.thread_id

        yield vsp_event

    # ==================== THINKING PART HOOKS ====================

    async def handle_thinking_start(self, part: ThinkingPart, index: int) -> AsyncIterator[dict]:
        """Emit reasoning-start event and register part."""
        part_id = f"{self.message_id}_thinking_{index}"
        self._active_parts[index] = {"id": part_id, "type": "thinking"}

        logger.info(
            f"[THINKING PART START] idx: {index}, content: {repr(part.content)[:200] if part.content else 'None'}"
        )

        # Emit reasoning-start (boundary event)
        event = {"type": "reasoning-start", "id": part_id}
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id
        yield event

        # If initial content exists, emit it as delta
        if part.content:
            logger.info(f"[THINKING PART] Emitting initial delta, len: {len(part.content)}")
            yield {"type": "reasoning-delta", "id": part_id, "delta": part.content}

    async def handle_thinking_delta(
        self, delta: ThinkingPartDelta, part_info: dict
    ) -> AsyncIterator[dict]:
        """Emit reasoning-delta event."""
        if delta.content_delta:
            yield {"type": "reasoning-delta", "id": part_info["id"], "delta": delta.content_delta}

    async def handle_thinking_end(self, part_info: dict) -> AsyncIterator[dict]:
        """Emit reasoning-end event."""
        event = {"type": "reasoning-end", "id": part_info["id"]}
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id
        yield event

    # ==================== MODEL RESPONSE HOOKS ====================

    async def handle_model_response(self, model_response) -> AsyncIterator[dict]:
        """Emit chimera-app-usage event with token usage from model response.

        This emits per-API-call usage data as soon as it becomes available
        from the model response, allowing clients to track token consumption
        in real-time.

        Args:
            model_response: ModelResponse from Pydantic AI with usage attribute

        Yields:
            chimera-app-usage event with token usage data
        """
        if not hasattr(model_response, "usage"):
            return

        usage = model_response.usage
        if usage is None:
            return

        # Safely extract documented RequestUsage fields
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_write_tokens = getattr(usage, "cache_write_tokens", 0) or 0
        cache_read_tokens = getattr(usage, "cache_read_tokens", 0) or 0
        input_audio_tokens = getattr(usage, "input_audio_tokens", 0) or 0
        cache_audio_read_tokens = getattr(usage, "cache_audio_read_tokens", 0) or 0
        output_audio_tokens = getattr(usage, "output_audio_tokens", 0) or 0

        # Compute total tokens from all token fields
        total_tokens = (
            input_tokens
            + output_tokens
            + cache_write_tokens
            + cache_read_tokens
            + input_audio_tokens
            + cache_audio_read_tokens
            + output_audio_tokens
        )

        # Build usage event with core fields
        event = {
            "type": "chimera-app-usage",
            "messageId": self.message_id,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheWriteTokens": cache_write_tokens,
            "cacheReadTokens": cache_read_tokens,
            "totalTokens": total_tokens,
        }

        # Include audio tokens only if present
        if input_audio_tokens:
            event["inputAudioTokens"] = input_audio_tokens
        if cache_audio_read_tokens:
            event["cacheAudioReadTokens"] = cache_audio_read_tokens
        if output_audio_tokens:
            event["outputAudioTokens"] = output_audio_tokens

        # Include details if present (e.g., reasoning_tokens)
        details = getattr(usage, "details", None)
        if details:
            event["details"] = details

        # Include threadId (boundary event)
        if self.include_thread_id and self.thread_id:
            event["threadId"] = self.thread_id

        yield event


def create_vsp_stream(
    message_id: str, thread_id: str = "", include_thread_id: bool = True
) -> VSPEventStream:
    """Factory function to create a VSPEventStream.

    Args:
        message_id: Unique message ID for this response
        thread_id: Optional thread ID to include in boundary events
        include_thread_id: Whether to include threadId in boundary events

    Returns:
        Configured VSPEventStream instance
    """
    return VSPEventStream(
        message_id=message_id, thread_id=thread_id, include_thread_id=include_thread_id
    )
