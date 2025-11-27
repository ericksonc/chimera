"""Multi-thread streaming transport for Chimera.

This module provides server-side multiplexing of multiple thread streams
into a single SSE connection, with client-side demultiplexing support.

Architecture:
- Server: /api/chat/threads endpoint accepts multiple thread IDs
- Server: Executes threads concurrently using asyncio
- Server: Multiplexes with round-robin interleaving
- Server: Annotates all chunks with thread_id
- Client: Demultiplexes by thread_id and routes to correct handler
"""

import asyncio
import json
import logging
from typing import AsyncIterator, List

from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from chimera_api.stream_handler import generate_vsp_events
from chimera_core.types import UserInput
from chimera_core.ui.vsp_events import DataThreadFinishEvent, DataThreadStartEvent

logger = logging.getLogger(__name__)


class MultiThreadChatRequest(BaseModel):
    """Request model for multi-thread chat endpoint.

    Attributes:
        thread_ids: List of thread IDs to execute concurrently
        messages: User messages to send to all threads
        user_input: Typed user input (message or deferred tools)
    """

    thread_ids: List[str]
    messages: List[dict]
    user_input: UserInput


async def handle_multi_thread_chat(request: MultiThreadChatRequest) -> EventSourceResponse:
    """Main endpoint handler for multi-thread streaming.

    Accepts multiple thread IDs, executes them concurrently,
    and multiplexes their output streams with round-robin interleaving.

    Args:
        request: MultiThreadChatRequest with thread IDs and messages

    Returns:
        EventSourceResponse with multiplexed SSE stream
    """
    logger.info(f"Multi-thread chat request: {len(request.thread_ids)} threads")

    # Create stream generators for each thread
    thread_streams = [stream_thread(thread_id, request) for thread_id in request.thread_ids]

    # Multiplex all streams
    multiplexed = multiply_streams(*thread_streams)

    # Return as SSE
    return EventSourceResponse(
        multiplexed,
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
        },
    )


async def stream_thread(thread_id: str, request: MultiThreadChatRequest) -> AsyncIterator[dict]:
    """Execute a single thread and yield VSP event dicts with thread_id annotation.

    Uses generate_vsp_events() to get raw dicts, avoiding SSE round-tripping.
    Wraps errors to isolate thread failures. Emits thread lifecycle events
    (start/finish) and annotates all chunks with thread_id.

    Args:
        thread_id: ID of the thread to execute
        request: Original multi-thread request (contains messages and user_input)

    Yields:
        VSP event dicts with thread_id annotation
    """
    try:
        # Emit thread start event (typed)
        start_event = DataThreadStartEvent(thread_id=thread_id)
        yield start_event.model_dump(by_alias=True, exclude_none=True)

        # For now, use empty thread protocol (new conversation)
        # In future, could load existing thread state from storage
        thread_protocol = []

        # Execute thread using raw event stream (no SSE parsing needed)
        async for event in generate_vsp_events(thread_protocol, request.user_input):
            # Annotate with thread_id
            event["threadId"] = thread_id
            yield event

        # Emit thread finish event (typed)
        finish_event = DataThreadFinishEvent(thread_id=thread_id)
        yield finish_event.model_dump(by_alias=True, exclude_none=True)

    except asyncio.CancelledError:
        logger.info(f"Thread {thread_id} cancelled")
        yield {"type": "error", "thread_id": thread_id, "error_text": "Thread execution cancelled"}
        raise
    except Exception as e:
        logger.error(f"Thread {thread_id} failed", exc_info=e)
        yield {"type": "error", "thread_id": thread_id, "error_text": f"Thread error: {str(e)}"}


async def multiply_streams(*streams: AsyncIterator[dict]) -> AsyncIterator[str]:
    """Multiplex multiple async iterators using efficient event-driven interleaving.

    Yields SSE-formatted strings (data: {...}\n\n). Uses asyncio.Queue for
    each stream with asyncio.wait() to efficiently block until ANY queue has data.
    No busy-waiting - only consumes CPU when events arrive.

    Args:
        *streams: Variable number of async iterators yielding event dicts

    Yields:
        SSE-formatted strings
    """
    if not streams:
        yield "data: [DONE]\n\n"
        return

    # Create tasks to buffer each stream into a queue
    queue_task_pairs = [_stream_to_queue(stream) for stream in streams]
    pairs = await asyncio.gather(*queue_task_pairs)

    # Extract queues and tasks
    active_queues = [pair[0] for pair in pairs]
    consumer_tasks = [pair[1] for pair in pairs]

    try:
        while active_queues:
            # Create get() tasks for all active queues
            pending_gets = {asyncio.create_task(queue.get()): queue for queue in active_queues}

            if not pending_gets:
                break

            # Wait for ANY queue to have data (efficient, no busy-wait)
            done, pending = await asyncio.wait(
                pending_gets.keys(), return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending get() tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Process completed tasks
            for task in done:
                queue = pending_gets[task]
                try:
                    chunk = await task

                    if chunk is None:  # Stream finished sentinel
                        active_queues.remove(queue)
                    else:
                        # Yield as SSE format
                        yield f"data: {json.dumps(chunk)}\n\n"

                except Exception as e:
                    logger.error(f"Error reading from queue: {e}")
                    if queue in active_queues:
                        active_queues.remove(queue)
    finally:
        # Cleanup: cancel all consumer tasks
        for task in consumer_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # Emit termination marker
    yield "data: [DONE]\n\n"


async def _stream_to_queue(
    stream: AsyncIterator[dict], maxsize: int = 10
) -> tuple[asyncio.Queue, asyncio.Task]:
    """Buffer stream into queue for concurrent consumption.

    Args:
        stream: Async iterator yielding event dicts
        maxsize: Maximum queue size for backpressure

    Returns:
        Tuple of (queue, consumer_task) for proper lifecycle management
    """
    queue = asyncio.Queue(maxsize=maxsize)

    async def _consumer():
        try:
            async for chunk in stream:
                await queue.put(chunk)
            # Sentinel to indicate stream finished naturally
            await queue.put(None)
        except asyncio.CancelledError:
            # Do not put sentinel if cancelled - avoids deadlock if queue is full
            raise
        except Exception as e:
            logger.error(f"Stream consumer error: {e}")
            # Attempt to signal error state, but don't block if queue is full
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # Start consumer task and return it for tracking
    task = asyncio.create_task(_consumer())
    return (queue, task)
