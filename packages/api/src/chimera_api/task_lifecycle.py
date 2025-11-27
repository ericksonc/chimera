"""Task lifecycle management for stream_handler.

This module provides structured resource management for async tasks,
ensuring proper cleanup even when errors occur.

Addresses Issue #40: Error Handling and Cleanup Complexity
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chimera_api.stream_handler import ActiveTaskRegistry

logger = logging.getLogger(__name__)


class TaskLifecycle:
    """Context manager for async task lifecycle and cleanup.

    This class guarantees proper task registration, execution, and cleanup,
    even when errors occur. It replaces nested try/except blocks with a
    clean context manager pattern.

    Usage:
        task = asyncio.create_task(some_async_function())
        async with TaskLifecycle(task_id="thread-123", task=task, registry=task_registry):
            # Task is registered and will be cleaned up automatically
            await task

    Benefits:
    - Guaranteed cleanup even on errors
    - No nested try/except blocks
    - Clear separation of concerns (lifecycle vs. business logic)
    - Proper error propagation
    """

    def __init__(
        self,
        task_id: str,
        task: asyncio.Task,
        registry: "ActiveTaskRegistry",
        cleanup_timeout: float = 1.0,
    ):
        """Initialize task lifecycle manager.

        Args:
            task_id: Unique identifier for this task (e.g., thread_id)
            task: The asyncio.Task to manage
            registry: ActiveTaskRegistry for cancellation support
            cleanup_timeout: Max seconds to wait for task cancellation (default 1.0)
        """
        self.task_id = task_id
        self.task = task
        self.registry = registry
        self.cleanup_timeout = cleanup_timeout

    async def __aenter__(self):
        """Register task with registry.

        Returns:
            self for 'async with ... as' syntax
        """
        await self.registry.register(self.task_id, self.task)
        logger.debug(f"[thread:{self.task_id}] Task registered")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup task and unregister from registry.

        This method guarantees cleanup even if:
        - The task raised an exception
        - The task was cancelled
        - Cleanup itself encounters errors

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)

        Returns:
            False to propagate exceptions (don't suppress them)
        """
        # Log exit reason
        if exc_type is asyncio.CancelledError:
            logger.debug(f"[thread:{self.task_id}] Task cancelled by user")
        elif exc_type is not None:
            logger.error(f"[thread:{self.task_id}] Task failed with {exc_type.__name__}: {exc_val}")
        else:
            logger.debug(f"[thread:{self.task_id}] Task completed successfully")

        # Unregister from registry (defensive - catch any errors)
        try:
            await self.registry.unregister(self.task_id)
        except Exception as e:
            logger.error(f"[thread:{self.task_id}] Failed to unregister task: {e}")

        # Clean up task if still running (defensive - catch any errors)
        if not self.task.done():
            try:
                self.task.cancel()
                await asyncio.wait_for(self.task, timeout=self.cleanup_timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f"[thread:{self.task_id}] Task didn't respond to cancel within "
                    f"{self.cleanup_timeout}s"
                )
            except asyncio.CancelledError:
                # Expected when task is cancelled
                pass
            except Exception as e:
                logger.error(f"[thread:{self.task_id}] Error during task cleanup: {e}")

        # Return False to propagate exceptions (don't suppress them)
        # This ensures CancelledError and other exceptions bubble up correctly
        return False
