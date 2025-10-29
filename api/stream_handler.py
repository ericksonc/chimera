"""Stream handler for bridging process_graph execution with VSP streaming.

This module provides the infrastructure to:
1. Run process_graph in an asyncio.Task (for cancellation)
2. Stream events via asyncio.Queue (decouples execution from SSE)
3. Track active tasks for cancellation support
"""

import asyncio
import json
import os
import uuid
from typing import AsyncIterator, Dict, Optional
from datetime import datetime, timezone
from pathlib import Path

from core.thread import process_graph, ProcessStart, ThreadState, ThreadDeps
from core.threadprotocol import ThreadProtocolWriter


class ActiveTaskRegistry:
    """Registry for tracking active process tasks.

    This allows the /cancel endpoint to find and cancel running tasks.
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


def create_emit_vsp_event(event_queue: asyncio.Queue, thread_id: str):
    """Factory function to create emit_vsp_event with closure over queue and thread_id.

    Args:
        event_queue: Queue to put VSP events into
        thread_id: Thread ID to include in boundary events

    Returns:
        Async function that emits VSP events
    """
    async def emit_vsp_event(event: dict, include_thread_id: bool = True):
        """Emit a VSP event to be streamed.

        Args:
            event: The VSP event dict
            include_thread_id: Whether to include threadId in this event.
                              Default True for most events (boundary events: start, turn boundaries, mutations).
                              Set to False for deltas (text-delta, tool-input-delta, reasoning-delta)
                              which reference by part ID instead.
        """
        if include_thread_id:
            event["threadId"] = thread_id
        await event_queue.put(event)

    return emit_vsp_event


def create_emit_threadprotocol_event(
    thread_writer: Optional[ThreadProtocolWriter],
    emit_vsp_event_fn
):
    """Factory function to create emit_threadprotocol_event with closure over writer.

    Args:
        thread_writer: ThreadProtocol writer for persistence (optional)
        emit_vsp_event_fn: VSP emit function for streaming

    Returns:
        Async function that emits ThreadProtocol events
    """
    async def emit_threadprotocol_event(event: dict):
        """Write to ThreadProtocol AND emit as VSP if appropriate.

        Some events go to both JSONL persistence and VSP streaming.
        Others (like internal state) might only go to JSONL.
        """
        # Write to ThreadProtocol (persistence)
        if thread_writer:
            await thread_writer.write_event(event)

        # Determine if this should also stream via VSP
        # Thread-level and turn-level events always include threadId
        if event.get("event_type") == "data-app-chimera":
            # State mutations: include threadId (boundary event)
            vsp_event = {
                "type": "data-app-chimera",
                "event_source": event["event_source"],
                "mutation_description": event["mutation_description"],
                "data": event["data"]
            }
            if "triggered_by_agent_id" in event:
                vsp_event["triggered_by_agent_id"] = event["triggered_by_agent_id"]
            await emit_vsp_event_fn(vsp_event, include_thread_id=True)

    return emit_threadprotocol_event


async def run_process_with_streaming(
    user_input: str,
    thread_id: Optional[str] = None
) -> tuple[asyncio.Task, asyncio.Queue]:
    """Run process_graph in a cancellable task with event streaming.

    Returns:
        - The asyncio.Task running the process (can be cancelled)
        - The Queue receiving VSP events to stream
    """
    # Create event queue for streaming
    event_queue = asyncio.Queue()

    # Generate thread ID if not provided
    if not thread_id:
        thread_id = f"thread_{uuid.uuid4().hex}"

    # Create ThreadProtocol writer
    threads_dir = Path(os.getenv("THREADS_DIR", "data/threads"))
    threads_dir.mkdir(parents=True, exist_ok=True)
    thread_file = threads_dir / f"{thread_id}.jsonl"
    thread_writer = None  # TODO: Initialize ThreadProtocolWriter

    # Create emit functions using factory pattern
    emit_vsp_event_fn = create_emit_vsp_event(event_queue, thread_id)
    emit_threadprotocol_event_fn = create_emit_threadprotocol_event(
        thread_writer,
        emit_vsp_event_fn
    )

    # Create ThreadDeps with emit methods
    deps = ThreadDeps(
        emit_threadprotocol_event=emit_threadprotocol_event_fn,
        emit_vsp_event=emit_vsp_event_fn
    )

    # TODO: Create proper ThreadState with all required components
    # For now this is a stub showing the pattern
    state = ThreadState(
        thread_id=uuid.UUID(thread_id.replace("thread_", "").replace("-", "")),
        active_space=None,  # TODO: Initialize ActiveSpace
        # ... other required fields
    )

    # Define the async function to run in the task
    async def run_graph():
        try:
            # Emit start event (boundary event, includes threadId by default)
            message_id = f"msg_{uuid.uuid4().hex}"
            await emit_vsp_event_fn({
                "type": "start",
                "messageId": message_id
            })

            # Run the graph with ProcessStart node
            result = await process_graph.run(
                ProcessStart(user_input=user_input, user_id=uuid.UUID(int=0)),
                state=state,
                deps=deps
            )

            # Emit finish event (boundary event, includes threadId by default)
            await emit_vsp_event_fn({"type": "finish"})

        except asyncio.CancelledError:
            # User clicked stop button
            await emit_vsp_event_fn({
                "type": "error",
                "errorText": "Cancelled by user"
            })
            raise  # Re-raise to properly cancel the task
        except Exception as e:
            # Other errors
            await emit_vsp_event_fn({
                "type": "error",
                "errorText": str(e)
            })
            raise
        finally:
            # Signal end of stream
            await event_queue.put(None)  # Sentinel value

    # Create and start the task
    task = asyncio.create_task(run_graph())

    # Register for cancellation
    await task_registry.register(thread_id, task)

    # Clean up registration when done
    def cleanup_callback(t):
        asyncio.create_task(task_registry.unregister(thread_id))
    task.add_done_callback(cleanup_callback)

    return task, event_queue


async def stream_vsp_from_queue(queue: asyncio.Queue) -> AsyncIterator[str]:
    """Convert queue events to VSP SSE format.

    This generator pulls events from the queue and formats them
    as Server-Sent Events for the HTTP response.
    """
    while True:
        event = await queue.get()

        # Check for sentinel (end of stream)
        if event is None:
            yield 'data: [DONE]\n\n'
            break

        # Format as SSE
        yield f'data: {json.dumps(event)}\n\n'


async def generate_vsp_with_cancellation(
    messages: list,
    thread_id: Optional[str] = None
) -> AsyncIterator[str]:
    """Generate VSP stream with cancellation support.

    This is the main entry point from the API endpoint.
    It orchestrates the process execution and streaming.
    """
    # Extract user input from messages
    # TODO: Build proper conversation history from messages
    user_messages = [m for m in messages if m.role == "user"]
    user_input = user_messages[-1].content if user_messages else "Hello"

    # Start the process in a task
    task, event_queue = await run_process_with_streaming(
        user_input=user_input,
        thread_id=thread_id
    )

    try:
        # Stream events from the queue
        async for sse_line in stream_vsp_from_queue(event_queue):
            yield sse_line
    finally:
        # If streaming stops for any reason, ensure task is cleaned up
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# NOTE: ActiveSpaceStreamingMixin is now obsolete - streaming is implemented
# directly in Agent.run_stream() (core/agent.py) using ctx.deps.emit_* methods.
# This stub remains for reference but should be removed once fully replaced.