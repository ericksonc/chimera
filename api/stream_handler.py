"""Stream handler for bridging process_graph execution with VSP streaming.

This module provides the infrastructure to:
1. Run process_graph in an asyncio.Task (for cancellation)
2. Stream events via asyncio.Queue (decouples execution from SSE)
3. Track active tasks for cancellation support
"""

import asyncio
import json
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


class StreamingThreadState(ThreadState):
    """Extended ThreadState that can emit events to a queue.

    This subclass adds an event queue that allows the graph nodes
    to emit events that will be streamed to the client.
    """
    def __init__(self, *args, event_queue: asyncio.Queue, thread_id: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_queue = event_queue
        self.thread_id = thread_id
        self.message_id = f"msg_{uuid.uuid4().hex}"

    async def emit_vsp_event(self, event: dict, include_thread_id: bool = False):
        """Emit a VSP event to be streamed.

        Args:
            event: The VSP event dict
            include_thread_id: Whether to include threadId in this event.
                              Set to True for boundary events (start, turn boundaries, mutations)
                              Set to False for deltas and end events (they reference by ID)
        """
        if include_thread_id:
            event["threadId"] = self.thread_id
        await self.event_queue.put(event)

    async def emit_threadprotocol_event(self, event: dict):
        """Write to ThreadProtocol AND emit as VSP if appropriate.

        Some events go to both JSONL persistence and VSP streaming.
        Others (like internal state) might only go to JSONL.
        """
        # Write to ThreadProtocol (persistence)
        if hasattr(self, '_thread_writer'):
            await self._thread_writer.write_event(event)

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
            await self.emit_vsp_event(vsp_event, include_thread_id=True)


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
    threads_dir = Path("data/threads")  # TODO: Make configurable via env var
    threads_dir.mkdir(parents=True, exist_ok=True)
    thread_file = threads_dir / f"{thread_id}.jsonl"

    # TODO: Create proper ThreadState with all required components
    # For now this is a stub showing the pattern
    state = StreamingThreadState(
        id=uuid.UUID(thread_id.replace("thread_", "").replace("-", "")),
        event_queue=event_queue,
        thread_id=thread_id,
        # ... other required fields
    )

    # Create ThreadDeps
    deps = ThreadDeps()

    # Define the async function to run in the task
    async def run_graph():
        try:
            # Emit start event (boundary event: include threadId)
            await state.emit_vsp_event({
                "type": "start",
                "messageId": state.message_id
            }, include_thread_id=True)

            # Run the graph with ProcessStart node
            result = await process_graph.run(
                ProcessStart(user_input=user_input, user_id=uuid.UUID(int=0)),
                state=state,
                deps=deps
            )

            # Emit finish event (boundary event: include threadId)
            await state.emit_vsp_event({"type": "finish"}, include_thread_id=True)

        except asyncio.CancelledError:
            # User clicked stop button
            await state.emit_vsp_event({
                "type": "error",
                "errorText": "Cancelled by user"
            }, include_thread_id=True)
            raise  # Re-raise to properly cancel the task
        except Exception as e:
            # Other errors
            await state.emit_vsp_event({
                "type": "error",
                "errorText": str(e)
            }, include_thread_id=True)
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


# TODO: Move this to a proper location when ActiveSpace is implemented
class ActiveSpaceStreamingMixin:
    """Mixin for ActiveSpace to handle streaming.

    This shows how run_stream would emit events during agent execution.
    Demonstrates the threadId pattern: include on boundary events, omit on deltas.
    """
    async def run_stream(self, state: StreamingThreadState):
        """Run agent with streaming, emitting VSP events as we go."""
        # Emit agent turn start (boundary event: include threadId)
        # This goes to both ThreadProtocol JSONL and VSP stream
        await state.emit_threadprotocol_event({
            "event_type": "agent_turn_start",
            "agent_id": str(self.active_agent.agent_id),
            "agent_name": self.active_agent.name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        # Also emit as VSP event with threadId
        await state.emit_vsp_event({
            "type": "agent-turn-start",
            "agentId": str(self.active_agent.agent_id),
            "agentName": self.active_agent.name
        }, include_thread_id=True)

        # Create text part ID for streaming
        text_part_id = f"{state.message_id}_text_0"

        # Emit text-start (boundary event: include threadId to establish mapping)
        await state.emit_vsp_event({
            "type": "text-start",
            "id": text_part_id
        }, include_thread_id=True)

        # TODO: Actually run agent.iter() here
        # async for event in self.pai_agent.iter(...):
        #     if isinstance(event, PartDeltaEvent):
        #         # Stream text delta (NO threadId - client knows the mapping)
        #         await state.emit_vsp_event({
        #             "type": "text-delta",
        #             "id": text_part_id,
        #             "delta": event.delta.content_delta
        #         }, include_thread_id=False)

        # For now, emit stub deltas (no threadId on deltas!)
        await state.emit_vsp_event({
            "type": "text-delta",
            "id": text_part_id,
            "delta": "This would be streamed "
        }, include_thread_id=False)

        await state.emit_vsp_event({
            "type": "text-delta",
            "id": text_part_id,
            "delta": "from agent.iter()"
        }, include_thread_id=False)

        # Close text part (no threadId - references by part ID)
        await state.emit_vsp_event({
            "type": "text-end",
            "id": text_part_id
        }, include_thread_id=False)

        # Emit agent turn end (boundary event: include threadId)
        await state.emit_threadprotocol_event({
            "event_type": "agent_turn_end",
            "agent_id": str(self.active_agent.agent_id),
            "completion_status": "complete",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        # Also emit as VSP event with threadId
        await state.emit_vsp_event({
            "type": "agent-turn-end",
            "agentId": str(self.active_agent.agent_id),
            "completionStatus": "complete"
        }, include_thread_id=True)

        # Return mock result for now
        return {"mock": "result"}