"""State reconstruction from ThreadProtocol events.

This module provides a generic pattern for reconstructing component state
from ThreadProtocol event history. Any stateful component (spaces, widgets, etc.)
can use StateReconstructor to replay mutations and rebuild their state.

Key design principles:
- Protocol-based: Works with any component implementing the Reconstructible protocol
- O(1) mutation routing: Map-based lookups instead of iteration
- Single responsibility: Only handles mutation replay, not event emission or task orchestration
- Reusable: Can be used by any stateful component, not just spaces
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class Reconstructible(Protocol):
    """Protocol for components that can reconstruct state from mutations.

    Any component (Space, Widget, etc.) that needs to replay state from
    ThreadProtocol should implement this protocol.
    """

    def apply_mutation(self, mutation_data: Any) -> None:
        """Apply a mutation to rebuild state.

        Args:
            mutation_data: The mutation payload (component-specific format)
        """
        ...

    @property
    def event_source_prefix(self) -> str:
        """The event_source prefix this component handles.

        Examples:
            - "space" (matches "space:MultiAgentSpace:123")
            - "widget:TodoWidget:abc" (exact match for specific widget instance)

        Returns:
            String prefix for routing mutations to this component
        """
        ...


@dataclass
class ReconstructionResult:
    """Result of state reconstruction process."""

    total_events: int
    mutations_applied: int
    mutations_skipped: int
    errors: List[str]

    @property
    def success(self) -> bool:
        """Returns True if reconstruction completed without errors."""
        return len(self.errors) == 0


class StateReconstructor:
    """Reconstruct component state from ThreadProtocol events.

    This class provides a generic pattern for replaying mutations from
    ThreadProtocol history to rebuild the current state of stateful components.

    Usage:
        # Register components that need state reconstruction
        reconstructor = StateReconstructor()
        reconstructor.register(active_space)
        reconstructor.register(todo_widget)

        # Reconstruct state from history
        result = reconstructor.reconstruct(history_events, thread_id="abc123")

        if not result.success:
            logger.error(f"Reconstruction errors: {result.errors}")
    """

    def __init__(self, thread_id: Optional[str] = None):
        """Initialize StateReconstructor.

        Args:
            thread_id: Optional thread ID for logging context
        """
        self._components: Dict[str, Reconstructible] = {}
        self._thread_id = thread_id or "unknown"

    def register(self, component: Reconstructible) -> None:
        """Register a component for state reconstruction.

        The component will receive mutations matching its event_source_prefix.

        Args:
            component: Component implementing Reconstructible protocol
        """
        prefix = component.event_source_prefix
        self._components[prefix] = component

        logger.info(
            f"[thread:{self._thread_id}] Registered component for reconstruction: "
            f"prefix={prefix} type={type(component).__name__}"
        )

    def reconstruct(
        self, events: List[dict], thread_id: Optional[str] = None
    ) -> ReconstructionResult:
        """Reconstruct state by replaying mutations from event history.

        Iterates through all events, finds data-app-chimera mutations,
        routes them to the appropriate component, and tracks results.

        Args:
            events: List of ThreadProtocol events (parsed JSONL)
            thread_id: Optional thread ID for logging (overrides constructor value)

        Returns:
            ReconstructionResult with statistics and any errors
        """
        if thread_id:
            self._thread_id = thread_id

        logger.info(
            f"[thread:{self._thread_id}] Starting state reconstruction: "
            f"events={len(events)} components={len(self._components)}"
        )

        mutations_applied = 0
        mutations_skipped = 0
        errors = []

        for event in events:
            if event.get("type") != "data-app-chimera":
                continue

            # v0.0.7 format: source and payload are nested inside data field
            data = event.get("data", {})
            event_source = data.get("source", "")
            mutation_data = data.get("payload", {})

            logger.debug(f"[thread:{self._thread_id}] Found mutation: source={event_source}")

            # Route mutation to appropriate component
            target = self._find_target(event_source)

            if target:
                try:
                    target.apply_mutation(mutation_data)
                    mutations_applied += 1

                    logger.debug(
                        f"[thread:{self._thread_id}] Applied mutation: "
                        f"source={event_source} target={type(target).__name__}"
                    )
                except Exception as e:
                    error_msg = f"Failed to apply mutation from {event_source}: {e}"
                    errors.append(error_msg)
                    logger.error(f"[thread:{self._thread_id}] {error_msg}")
            else:
                mutations_skipped += 1
                logger.warning(
                    f"[thread:{self._thread_id}] No target for mutation: source={event_source}"
                )

        result = ReconstructionResult(
            total_events=len(events),
            mutations_applied=mutations_applied,
            mutations_skipped=mutations_skipped,
            errors=errors,
        )

        logger.info(
            f"[thread:{self._thread_id}] Reconstruction complete: "
            f"applied={mutations_applied} skipped={mutations_skipped} "
            f"errors={len(errors)}"
        )

        return result

    def _find_target(self, event_source: str) -> Optional[Reconstructible]:
        """Find the component that should handle this mutation.

        Uses O(1) map-based lookup strategy:
        1. Try exact match (for widget-specific instances)
        2. Try component type match (first part before ':')

        Args:
            event_source: Event source string (e.g., "space:MultiAgentSpace:123")

        Returns:
            Component that handles this mutation, or None if not found
        """
        # Try exact match first (for widgets with specific instance IDs)
        if event_source in self._components:
            return self._components[event_source]

        # Try component type match (first part of event_source)
        if ":" in event_source:
            component_type = event_source.split(":")[0]
            return self._components.get(component_type)

        # Fallback: treat entire source as component type
        return self._components.get(event_source)

    def clear(self) -> None:
        """Clear all registered components."""
        self._components.clear()
        logger.info(f"[thread:{self._thread_id}] Cleared all registered components")
