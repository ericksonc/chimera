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
from core.threadprotocol.writer import ThreadProtocolWriter


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


async def generate_vsp(
    thread_jsonl: list[dict],
    user_input: str
) -> AsyncIterator[str]:
    """Generate VSP stream from ThreadProtocol JSONL.

    The client provides full ThreadProtocol history, we reconstruct state
    from it, process the new user input, and stream back VSP events.

    Args:
        thread_jsonl: List of ThreadProtocol event dicts (parsed JSONL lines)
        user_input: New user input to process

    Yields:
        SSE-formatted VSP events
    """
    from uuid import UUID
    from core.threadprotocol.blueprint import Blueprint
    from core.spaces.generic_space import GenericSpace
    from core.agent import Agent
    from core.thread import ThreadState, ThreadDeps, ProcessStart, process_graph

    # Create event queue for streaming
    event_queue = asyncio.Queue()

    # Parse ThreadProtocol - first line is BlueprintProtocol
    if not thread_jsonl:
        raise ValueError("ThreadProtocol cannot be empty - must have BlueprintProtocol")

    blueprint_event = thread_jsonl[0]
    if blueprint_event.get("event_type") != "thread_blueprint":
        raise ValueError("First ThreadProtocol event must be thread_blueprint")

    # Extract thread_id from blueprint
    thread_id = blueprint_event.get("thread_id")
    if not thread_id:
        thread_id = str(uuid.uuid4())

    # Parse BlueprintProtocol to create Blueprint object
    blueprint = Blueprint.from_dict(blueprint_event["blueprint"])

    # Reconstruct agents from blueprint using from_blueprint_config
    agents_by_id = {}
    for agent_config in blueprint.agents:
        if agent_config.type == "inline":
            # Create agent from inline config
            agent = Agent(
                id=UUID(agent_config.id),
                name=agent_config.name,
                description=agent_config.description,
                base_prompt=agent_config.base_prompt
            )
            # TODO: Reconstruct agent widgets using Widget.from_blueprint_config
            # for widget_config in agent_config.widgets:
            #     widget = load_widget_class(widget_config.class_name).from_blueprint_config(widget_config)
            #     agent.register_widget(widget)
            agents_by_id[str(agent.id)] = agent
        else:
            # Referenced agents would be loaded from registry
            # TODO: Implement agent registry loading via Agent.from_yaml()
            raise NotImplementedError("Referenced agents not yet implemented")

    # Reconstruct Space from blueprint using from_blueprint_config
    space_config = blueprint.space
    if space_config.type == "default":
        # Default to GenericSpace with single agent
        if len(agents_by_id) != 1:
            raise ValueError("Default space requires exactly one agent")
        agent = list(agents_by_id.values())[0]
        active_space = GenericSpace(agent)
    elif space_config.type == "reference":
        # Use from_blueprint_config to reconstruct the specific space
        if space_config.class_name == "chimera.spaces.GenericSpace":
            active_space = GenericSpace.from_blueprint_config(
                space_config,
                agents_by_id
            )
        else:
            # TODO: Dynamic space loading via importlib
            raise NotImplementedError(f"Space {space_config.class_name} not yet implemented")
    else:
        raise ValueError(f"Unknown space type: {space_config.type}")

    # TODO: Reconstruct space-level widgets using Widget.from_blueprint_config
    # for widget_config in space_config.widgets:
    #     widget = load_widget_class(widget_config.class_name).from_blueprint_config(widget_config)
    #     active_space.register_widget(widget)

    # Extract conversation history (all events after blueprint)
    history_events = thread_jsonl[1:] if len(thread_jsonl) > 1 else []

    # Define the async function to run
    async def run_graph():
        # No disk persistence - client owns ThreadProtocol
        # Create a no-op writer
        class NoOpWriter:
            async def write_event(self, event: dict):
                # Client will reconstruct from SSE stream
                pass

        writer = NoOpWriter()

        try:
            # Create emit functions using factory pattern
            emit_vsp_event_fn = create_emit_vsp_event(event_queue, thread_id)
            emit_threadprotocol_event_fn = create_emit_threadprotocol_event(
                writer,
                emit_vsp_event_fn
            )

            # Create ThreadDeps with emit methods
            deps = ThreadDeps(
                emit_threadprotocol_event=emit_threadprotocol_event_fn,
                emit_vsp_event=emit_vsp_event_fn,
                thread_writer=None  # No file persistence - client owns it
            )

            # Create ThreadState with reconstructed components
            # TODO: Properly reconstruct all ThreadState fields from history
            state = ThreadState(
                thread_id=UUID(thread_id) if thread_id else uuid.uuid4(),
                active_space=active_space,
                # TODO: Derive turn_number, parent_thread_id, depth from history
                # TODO: Apply any state mutations from history_events
            )

            # Emit start event
            message_id = f"msg_{uuid.uuid4().hex}"
            await emit_vsp_event_fn({
                "type": "start",
                "messageId": message_id
            })

            # Run the graph with user input
            # The Space's transformer will convert history_events to ModelMessages
            result = await process_graph.run(
                ProcessStart(user_input=user_input, user_id=UUID(int=0)),
                state=state,
                deps=deps
            )

            # Emit finish event
            await emit_vsp_event_fn({"type": "finish"})

        except asyncio.CancelledError:
            await emit_vsp_event_fn({
                "type": "error",
                "errorText": "Cancelled by user"
            })
            raise
        except Exception as e:
            await emit_vsp_event_fn({
                "type": "error",
                "errorText": str(e)
            })
            raise
        finally:
            # Signal end of stream
            await event_queue.put(None)

    # Create and start the task
    task = asyncio.create_task(run_graph())

    try:
        # Stream events from the queue
        async for sse_line in stream_vsp_from_queue(event_queue):
            yield sse_line
    finally:
        # Clean up task if needed
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass