"""Stream handler for bridging process_graph execution with VSP streaming.

This module provides the infrastructure to:
1. Run process_graph in an asyncio.Task (for cancellation)
2. Stream events via asyncio.Queue (decouples execution from SSE)
3. Track active tasks for cancellation support
4. Multi-thread streaming support via /api/chat/threads endpoint

Note: Event emission infrastructure (threadId injection, ThreadProtocol persistence,
mutation streaming) has been moved to core/ui/streaming_infrastructure.py per Issue #38.
This module now focuses purely on HTTP transport concerns.
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, Dict, Optional

from chimera_core.thread import ThreadDeps, run_thread
from chimera_core.threadprotocol.writer import NoOpThreadProtocolWriter
from chimera_core.types import UserInput
from chimera_core.ui import create_streaming_infrastructure

# Configure logger
logger = logging.getLogger(__name__)


def log_with_context(level: int, thread_id: str, msg: str, **kwargs):
    """Log with structured context for better debuggability.

    Args:
        level: Logging level (logging.INFO, logging.ERROR, etc.)
        thread_id: Thread ID for context
        msg: Log message
        **kwargs: Additional context key-value pairs
    """
    context = f"[thread:{thread_id}]"
    if kwargs:
        context_items = " ".join(f"{k}={v}" for k, v in kwargs.items())
        context = f"{context} {context_items}"
    logger.log(level, f"{context} {msg}")


class ActiveTaskRegistry:
    """Registry for tracking active process tasks.

    This allows the /halt endpoint to find and cancel running tasks.
    """

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def register(self, task_id: str, task: asyncio.Task):
        """Register an active task."""
        async with self._lock:
            self._tasks[task_id] = task

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task by ID. Returns True if found and cancelled."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and not task.done():
                task.cancel()
                return True
            return False

    async def unregister(self, task_id: str):
        """Remove a task from the registry (when complete or cancelled)."""
        async with self._lock:
            self._tasks.pop(task_id, None)

    async def cleanup_done_tasks(self):
        """Remove completed tasks from registry."""
        async with self._lock:
            done_ids = [tid for tid, task in self._tasks.items() if task.done()]
            for tid in done_ids:
                del self._tasks[tid]


# Global registry for active tasks
task_registry = ActiveTaskRegistry()


# NOTE: Event emission factories (create_emit_vsp_event, create_emit_threadprotocol_event)
# have been moved to core/ui/streaming_infrastructure.py per Issue #38.
# The StreamingInfrastructure class now handles:
# - ThreadId injection (intelligently - only if not already present)
# - ThreadProtocol persistence
# - Mutation streaming (data-app-chimera → VSP)
# - Configurable logging


async def stream_vsp_from_queue(
    queue: asyncio.Queue, timeout: float = 30.0, thread_id: Optional[str] = None
) -> AsyncIterator[str]:
    """Convert queue events to VSP SSE format.

    This generator pulls events from the queue and formats them
    as Server-Sent Events for the HTTP response.

    Args:
        queue: Queue to pull events from
        timeout: Maximum seconds to wait for each event (default 30s)
        thread_id: Optional thread ID for logging context
    """
    consecutive_full_queues = 0

    while True:
        # Monitor queue depth for backpressure detection
        queue_size = queue.qsize()
        if queue_size > 50:
            consecutive_full_queues += 1
            # Log every 10 occurrences to avoid log spam
            if consecutive_full_queues % 10 == 0:
                if thread_id:
                    log_with_context(
                        logging.WARNING,
                        thread_id,
                        "Queue backing up",
                        queue_size=queue_size,
                        consecutive=consecutive_full_queues,
                    )
                else:
                    logger.warning(
                        f"Queue backing up: {queue_size} items (consecutive warnings: {consecutive_full_queues})"
                    )
        else:
            consecutive_full_queues = 0

        try:
            event = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Queue timeout after {timeout}s - worker may have crashed")
            yield 'data: {"type":"error","errorText":"Internal timeout - worker unresponsive"}\n\n'
            break

        # Check for sentinel (end of stream)
        if event is None:
            yield "data: [DONE]\n\n"
            break

        # Format as SSE
        yield f"data: {json.dumps(event)}\n\n"


async def generate_vsp_events(
    thread_jsonl: list[dict], user_input: "UserInput"
) -> AsyncIterator[dict]:
    """Generate VSP events from ThreadProtocol JSONL (raw event dicts).

    This is the core event generation function that yields raw event dicts.
    For SSE streaming, use generate_vsp() which wraps this with SSE formatting.
    For multi-thread streaming, use this directly to avoid SSE round-tripping.

    The client provides full ThreadProtocol history, we reconstruct state
    from it, process the new user input, and stream back VSP events.

    This function registers the running task with the ActiveTaskRegistry,
    allowing the /halt endpoint to cancel it mid-execution.

    Args:
        thread_jsonl: List of ThreadProtocol event dicts (parsed JSONL lines)
        user_input: Discriminated union (UserInputMessage | UserInputDeferredTools)

    Yields:
        Raw VSP event dicts (not SSE-formatted)
    """
    from uuid import UUID

    from chimera_core.threadprotocol.blueprint import (
        Blueprint,
    )
    # ThreadState, ThreadDeps, run_thread already imported at top of file

    # Create event queue for streaming
    event_queue = asyncio.Queue()

    # Parse ThreadProtocol - first line is BlueprintProtocol
    if not thread_jsonl:
        raise ValueError("ThreadProtocol cannot be empty - must have BlueprintProtocol")

    blueprint_event = thread_jsonl[0]
    if blueprint_event.get("type") != "thread-blueprint":
        raise ValueError("First ThreadProtocol event must be thread-blueprint")

    # Extract threadId from blueprint (v0.0.6 camelCase)
    thread_id = blueprint_event.get("threadId")
    if not thread_id:
        thread_id = str(uuid.uuid4())

    # Parse BlueprintProtocol event to create Blueprint object
    blueprint = Blueprint.from_event(blueprint_event)

    # Reconstruct Space from blueprint using SpaceFactory (Issue #36)
    # SpaceFactory handles DefaultSpaceConfig vs ReferencedSpaceConfig logic
    from chimera_core.spaces import SpaceFactory

    active_space = SpaceFactory.from_blueprint_config(blueprint.space)

    # TODO: Reconstruct space-level widgets using Widget.from_blueprint_config
    # for widget_config in space_config.widgets:
    #     widget = load_widget_class(widget_config.class_name).from_blueprint_config(widget_config)
    #     active_space.register_widget(widget)

    # Extract conversation history (all events after blueprint)
    history_events = thread_jsonl[1:] if len(thread_jsonl) > 1 else []

    # NOTE: State reconstruction is now handled automatically in ThreadState.__init__()
    # (Issue #37) - no need to manually orchestrate it in the API layer

    # Define the async function to run
    async def run_graph():
        # No disk persistence - client owns ThreadProtocol
        # Create a no-op writer for both emit and deps
        writer = NoOpThreadProtocolWriter()

        try:
            # Create streaming infrastructure using core layer factory (Issue #38)
            # This encapsulates threadId injection, persistence, and mutation streaming
            infrastructure = create_streaming_infrastructure(
                thread_id=thread_id,
                event_queue=event_queue,
                thread_writer=writer,
            )

            # Create ThreadDeps with emit methods from infrastructure
            deps = ThreadDeps(
                emit_threadprotocol_event=infrastructure.emit_threadprotocol_event,
                emit_vsp_event=infrastructure.emit_vsp_event,
                thread_writer=writer,  # No file persistence - client reconstructs from SSE stream
                client_context=user_input.client_context,  # Propagate client context
            )

            # Emit start event
            message_id = f"msg_{uuid.uuid4().hex}"
            await infrastructure.emit_vsp_event({"type": "start", "messageId": message_id})

            # Run the thread with typed user input
            # The Space's transformer will convert history_events to ModelMessages
            # TODO: Derive parent_thread_id from history if present
            await run_thread(
                user_input=user_input,  # Typed discriminated union
                user_id=UUID(int=0),  # TODO: Get real user_id
                thread_id=UUID(thread_id) if thread_id else uuid.uuid4(),
                active_space=active_space,
                thread_builder=None,  # We're not using ThreadProtocol builder (client owns it)
                deps=deps,
                parent_thread_id=None,  # TODO: Extract from history if this is a child thread
                history_events=history_events,  # Pass conversation history to agent
            )

            # Emit finish event
            await infrastructure.emit_vsp_event({"type": "finish"})

        except asyncio.CancelledError:
            # User clicked halt/stop button
            log_with_context(logging.INFO, thread_id, "Execution cancelled by user")
            await infrastructure.emit_vsp_event(
                {"type": "error", "errorText": "Execution halted by user"}
            )
            raise
        except Exception as e:
            # Log full traceback for debugging
            import traceback

            log_with_context(logging.ERROR, thread_id, "Error in stream handler", error=str(e))
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            await infrastructure.emit_vsp_event({"type": "error", "errorText": str(e)})
            raise
        finally:
            # Signal end of stream
            await event_queue.put(None)

    # Create and start the task
    task = asyncio.create_task(run_graph())

    # Register task with registry for cancellation support
    await task_registry.register(thread_id, task)

    try:
        # Stream events from the queue (raw dicts, no SSE formatting)
        timeout = 30.0
        consecutive_full_queues = 0

        while True:
            # Monitor queue depth for backpressure detection
            queue_size = event_queue.qsize()
            if queue_size > 50:
                consecutive_full_queues += 1
                if consecutive_full_queues % 10 == 0:
                    log_with_context(
                        logging.WARNING,
                        thread_id,
                        "Queue backing up",
                        queue_size=queue_size,
                        consecutive=consecutive_full_queues,
                    )
            else:
                consecutive_full_queues = 0

            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Queue timeout after {timeout}s - worker may have crashed")
                yield {"type": "error", "errorText": "Internal timeout - worker unresponsive"}
                break

            # Check for sentinel (end of stream)
            if event is None:
                break

            # Yield raw event dict
            yield event

    finally:
        # Defensive cleanup - ensure cleanup always completes even if errors occur
        try:
            await task_registry.unregister(thread_id)
        except Exception as e:
            logger.error(f"Failed to unregister task {thread_id}: {e}")

        # Clean up task if needed
        if not task.done():
            try:
                task.cancel()
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning(f"Task {thread_id} didn't respond to cancel within 1s")
            except asyncio.CancelledError:
                # Expected when task is cancelled
                pass
            except Exception as e:
                logger.error(f"Error during task cleanup {thread_id}: {e}")


async def generate_vsp(thread_jsonl: list[dict], user_input: "UserInput") -> AsyncIterator[str]:
    """Generate VSP stream from ThreadProtocol JSONL (SSE-formatted).

    This wraps generate_vsp_events() and formats output as Server-Sent Events.
    For multi-thread streaming or other transports, use generate_vsp_events() directly.

    Args:
        thread_jsonl: List of ThreadProtocol event dicts (parsed JSONL lines)
        user_input: Discriminated union (UserInputMessage | UserInputDeferredTools)

    Yields:
        SSE-formatted VSP events
    """
    # Stream raw events and format as SSE
    async for event in generate_vsp_events(thread_jsonl, user_input):
        # Format as SSE
        yield f"data: {json.dumps(event)}\n\n"

    # Emit [DONE] marker
    yield "data: [DONE]\n\n"


async def run_triggered_thread(
    space,
    user_input: "UserInput",
    thread_id: str,
    blueprint_event: dict,
) -> str | None:
    """Run a triggered thread execution (non-streaming).

    This is used by the /trigger endpoint for scheduled/cron execution.
    Unlike generate_vsp_events, this doesn't stream - it runs to completion
    and returns the final result.

    Args:
        space: The Space instance to run
        user_input: UserInputScheduled with prompt and trigger context
        thread_id: Thread ID for this execution
        blueprint_event: The blueprint event dict (for history)

    Returns:
        The final output from the agent, or None if no output
    """
    from uuid import UUID

    # Create a no-op writer (we don't persist for triggered execution)
    writer = NoOpThreadProtocolWriter()

    # Create a dummy queue (we won't consume events, but infrastructure needs it)
    event_queue = asyncio.Queue()

    # Create streaming infrastructure (even though we won't stream)
    infrastructure = create_streaming_infrastructure(
        thread_id=thread_id,
        event_queue=event_queue,
        thread_writer=writer,
    )

    # Create ThreadDeps
    deps = ThreadDeps(
        emit_threadprotocol_event=infrastructure.emit_threadprotocol_event,
        emit_vsp_event=infrastructure.emit_vsp_event,
        thread_writer=writer,
        client_context=getattr(user_input, "trigger_context", None),
    )

    # History is just the blueprint event (fresh thread)
    history_events = []

    # Run the thread
    result = await run_thread(
        user_input=user_input,
        user_id=UUID(int=0),  # System user
        thread_id=UUID(thread_id),
        active_space=space,
        thread_builder=None,
        deps=deps,
        history_events=history_events,
    )

    return result
