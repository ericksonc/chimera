"""Base class for hook-based event stream transformation.

This module provides the foundation for transforming Pydantic AI events
into various UI streaming protocols using lifecycle hooks.
"""

import asyncio
import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

logger = logging.getLogger(__name__)


@dataclass
class UIEventStream(ABC):
    """Base class for hook-based event stream transformers.

    This class provides the framework for transforming Pydantic AI streaming
    events into UI protocol events (VSP, AG-UI, etc.) using lifecycle hooks.

    The pattern decomposes event transformation into specialized hook methods:
    - Stream-level hooks (before_stream, after_stream, on_error)
    - Turn-level hooks (before_request, after_request, before_response, after_response)
    - Part-level hooks (handle_text_start, handle_text_delta, etc.)

    Subclasses override only the hooks they need, enabling clean customization
    without modifying core orchestration logic.

    Example:
        >>> class VSPEventStream(UIEventStream):
        ...     async def before_stream(self):
        ...         yield {"type": "start", "messageId": self.message_id}
        ...
        ...     async def handle_text_delta(self, delta, part_info):
        ...         if delta.content_delta:
        ...             yield {"type": "text-delta", "id": part_info["id"], "delta": delta.content_delta}
    """

    # State tracking
    message_id: str
    _turn: str = "response"  # "request" or "response"
    _active_parts: dict[int, dict] = field(default_factory=dict)  # {index: {id, type, name, ...}}

    # ==================== STREAM-LEVEL HOOKS ====================

    async def before_stream(self) -> AsyncIterator[dict]:
        """Called once at stream start.

        Subclasses override to emit initial events (e.g., "start" chunk).

        Yields:
            Initial events to emit
        """
        return
        yield

    async def after_stream(self) -> AsyncIterator[dict]:
        """Called once at stream end (success or failure).

        Subclasses override to emit final events (e.g., "finish", "done").

        Yields:
            Final events to emit
        """
        return
        yield

    async def on_error(self, error: Exception) -> AsyncIterator[dict]:
        """Called if streaming fails.

        Args:
            error: The exception that occurred

        Yields:
            Error events to emit
        """
        logger.error(f"Stream error: {error}")
        return
        yield

    # ==================== TURN-LEVEL HOOKS ====================

    async def before_request(self) -> AsyncIterator[dict]:
        """Called before tool execution phase.

        Yields:
            Events to emit (e.g., "start-step")
        """
        return
        yield

    async def after_request(self) -> AsyncIterator[dict]:
        """Called after tool execution completes.

        Yields:
            Events to emit
        """
        return
        yield

    async def before_response(self) -> AsyncIterator[dict]:
        """Called before model generates response.

        Yields:
            Events to emit
        """
        return
        yield

    async def after_response(self) -> AsyncIterator[dict]:
        """Called after model response completes.

        Yields:
            Events to emit (e.g., "finish-step")
        """
        return
        yield

    # ==================== MODEL RESPONSE HOOKS ====================

    async def handle_model_response(self, model_response) -> AsyncIterator[dict]:
        """Called when a model response is available with usage data.

        This is typically called after a model request completes and we have
        access to the ModelResponse object with token usage information.

        Args:
            model_response: The ModelResponse object from Pydantic AI

        Yields:
            Events to emit (e.g., usage tracking events)
        """
        return
        yield

    # ==================== TURN TRANSITION ====================

    async def _turn_to(self, to_turn: str) -> AsyncIterator[dict]:
        """Transition between request/response turns.

        Calls appropriate after/before hooks for the transition.

        Args:
            to_turn: Target turn ("request" or "response")

        Yields:
            Events from transition hooks
        """
        if to_turn == self._turn:
            return

        # Exit current turn
        if self._turn == "request":
            async for e in self.after_request():
                yield e
        elif self._turn == "response":
            async for e in self.after_response():
                yield e

        # Transition
        self._turn = to_turn

        # Enter new turn
        if to_turn == "request":
            async for e in self.before_request():
                yield e
        elif to_turn == "response":
            async for e in self.before_response():
                yield e

    # ==================== PART-LEVEL HOOKS ====================

    async def handle_text_start(self, part: TextPart, index: int) -> AsyncIterator[dict]:
        """Called when a text part starts.

        Args:
            part: The TextPart that started
            index: Part index in the response

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_text_delta(self, delta: TextPartDelta, part_info: dict) -> AsyncIterator[dict]:
        """Called when text content arrives.

        Args:
            delta: The text delta
            part_info: Active part info dict with {id, type, ...}

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_text_end(self, part_info: dict) -> AsyncIterator[dict]:
        """Called when a text part completes.

        Args:
            part_info: Active part info dict with {id, type, ...}

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_tool_call_start(self, part: ToolCallPart, index: int) -> AsyncIterator[dict]:
        """Called when a tool call starts.

        Args:
            part: The ToolCallPart that started
            index: Part index in the response

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_tool_call_delta(
        self, delta: ToolCallPartDelta, part_info: dict
    ) -> AsyncIterator[dict]:
        """Called when tool call args arrive.

        Args:
            delta: The tool call args delta
            part_info: Active part info dict with {id, type, name, ...}

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_tool_call_available(self, event: FunctionToolCallEvent) -> AsyncIterator[dict]:
        """Called when tool call is about to execute.

        Args:
            event: The function tool call event

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_tool_result(self, event: FunctionToolResultEvent) -> AsyncIterator[dict]:
        """Called when tool execution completes.

        Args:
            event: The function tool result event

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_thinking_start(self, part: ThinkingPart, index: int) -> AsyncIterator[dict]:
        """Called when a thinking/reasoning part starts.

        Args:
            part: The ThinkingPart that started
            index: Part index in the response

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_thinking_delta(
        self, delta: ThinkingPartDelta, part_info: dict
    ) -> AsyncIterator[dict]:
        """Called when thinking/reasoning content arrives.

        Args:
            delta: The thinking delta
            part_info: Active part info dict with {id, type, ...}

        Yields:
            Events to emit
        """
        return
        yield

    async def handle_thinking_end(self, part_info: dict) -> AsyncIterator[dict]:
        """Called when a thinking part completes.

        Args:
            part_info: Active part info dict with {id, type, ...}

        Yields:
            Events to emit
        """
        return
        yield

    # ==================== EVENT DISPATCHING ====================

    async def handle_part_start(self, event: PartStartEvent) -> AsyncIterator[dict]:
        """Dispatch PartStartEvent to appropriate handler.

        Args:
            event: The part start event

        Yields:
            Events from the appropriate handler
        """
        idx = event.index
        part = event.part

        if isinstance(part, TextPart):
            async for e in self.handle_text_start(part, idx):
                yield e
        elif isinstance(part, ToolCallPart):
            async for e in self.handle_tool_call_start(part, idx):
                yield e
        elif isinstance(part, ThinkingPart):
            async for e in self.handle_thinking_start(part, idx):
                yield e

    async def handle_part_delta(self, event: PartDeltaEvent) -> AsyncIterator[dict]:
        """Dispatch PartDeltaEvent to appropriate handler.

        Args:
            event: The part delta event

        Yields:
            Events from the appropriate handler
        """
        idx = event.index
        delta = event.delta

        if idx not in self._active_parts:
            return

        part_info = self._active_parts[idx]

        if isinstance(delta, TextPartDelta):
            async for e in self.handle_text_delta(delta, part_info):
                yield e
        elif isinstance(delta, ToolCallPartDelta):
            async for e in self.handle_tool_call_delta(delta, part_info):
                yield e
        elif isinstance(delta, ThinkingPartDelta):
            async for e in self.handle_thinking_delta(delta, part_info):
                yield e

    async def close_active_parts(self) -> AsyncIterator[dict]:
        """Close all active parts after model request completes.

        Yields:
            End events for each active part
        """
        for idx, part_info in self._active_parts.items():
            if part_info["type"] == "text":
                async for e in self.handle_text_end(part_info):
                    yield e
            elif part_info["type"] == "thinking":
                async for e in self.handle_thinking_end(part_info):
                    yield e

        # Clear for next potential model request
        self._active_parts.clear()

    # ==================== MAIN TRANSFORM METHOD ====================

    async def transform_pai_stream(
        self, pai_agent_run, on_complete: Optional[callable] = None
    ) -> AsyncIterator[dict]:
        """Transform Pydantic AI agent run stream to UI protocol events.

        This is the main orchestration method that calls lifecycle hooks
        at appropriate points.

        Args:
            pai_agent_run: The async context manager from pai_agent.iter()
            on_complete: Optional callback when stream completes

        Yields:
            UI protocol events (dicts)
        """
        # Before stream
        async for e in self.before_stream():
            yield e

        try:
            # Emit start-step at beginning
            async for e in self._turn_to("response"):
                yield e

            # Iterate through execution nodes
            from pydantic_ai import Agent as PAIAgent

            async for node in pai_agent_run:
                # MODEL REQUEST NODE - Model is generating
                if PAIAgent.is_model_request_node(node):
                    async with node.stream(pai_agent_run.ctx) as stream:
                        async for event in stream:
                            if isinstance(event, PartStartEvent):
                                async for e in self.handle_part_start(event):
                                    yield e
                            elif isinstance(event, PartDeltaEvent):
                                async for e in self.handle_part_delta(event):
                                    yield e
                            elif isinstance(event, FinalResultEvent):
                                # Don't close parts yet - more deltas can come
                                pass

                        # After stream completes, close all active parts
                        async for e in self.close_active_parts():
                            yield e

                        # Emit usage event if model response has usage data
                        # This handles both tool-calling and pure text responses
                        model_response = stream.get()
                        if model_response and hasattr(model_response, "usage"):
                            async for e in self.handle_model_response(model_response):
                                yield e

                # TOOL EXECUTION NODE - Tools are being called
                elif PAIAgent.is_call_tools_node(node):
                    # Transition to request turn
                    async for e in self._turn_to("request"):
                        yield e

                    async with node.stream(pai_agent_run.ctx) as stream:
                        async for event in stream:
                            if isinstance(event, FunctionToolCallEvent):
                                async for e in self.handle_tool_call_available(event):
                                    yield e
                            elif isinstance(event, FunctionToolResultEvent):
                                async for e in self.handle_tool_result(event):
                                    yield e

                    # Transition back to response turn
                    async for e in self._turn_to("response"):
                        yield e

            # Stream completed successfully
            if on_complete:
                # Support async generator, async callable, or sync callable
                import inspect
                from concurrent.futures import ThreadPoolExecutor

                if inspect.isasyncgenfunction(on_complete):
                    async for e in on_complete(pai_agent_run.result):
                        yield e
                elif inspect.iscoroutinefunction(on_complete):
                    await on_complete(pai_agent_run.result)
                else:
                    # Run sync callable in executor
                    loop = asyncio.get_running_loop()
                    with ThreadPoolExecutor() as executor:
                        await loop.run_in_executor(executor, on_complete, pai_agent_run.result)

        except Exception as e:
            async for error_event in self.on_error(e):
                yield error_event
            raise

        finally:
            # After stream
            async for e in self.after_stream():
                yield e
