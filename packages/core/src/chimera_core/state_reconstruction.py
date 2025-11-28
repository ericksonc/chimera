"""State reconstruction from ThreadProtocol events.

This module provides a generic pattern for reconstructing component state
from ThreadProtocol event history. StatefulPlugin instances (spaces, widgets)
use StateReconstructor to replay mutations and rebuild their state.

Key design principles:
- Uses StatefulPlugin ABC for type safety (not duck-typing)
- O(1) mutation routing: Map-based lookups instead of iteration
- Single responsibility: Only handles mutation replay, not event emission
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from chimera_core.base_plugin import StatefulPlugin

logger = logging.getLogger(__name__)


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

    Replays mutations from ThreadProtocol history to rebuild StatefulPlugin state.

    Usage:
        reconstructor = StateReconstructor(thread_id="abc123")
        reconstructor.register(stateful_space)
        reconstructor.register(stateful_widget)
        result = reconstructor.reconstruct(history_events)
    """

    def __init__(self, thread_id: Optional[str] = None):
        """Initialize StateReconstructor.

        Args:
            thread_id: Optional thread ID for logging context
        """
        self._components: Dict[str, "StatefulPlugin[Any, Any]"] = {}
        self._thread_id = thread_id or "unknown"

    def register(self, component: "StatefulPlugin[Any, Any]") -> None:
        """Register a StatefulPlugin for state reconstruction.

        The component will receive mutations matching its event_source_prefix.

        Args:
            component: StatefulPlugin instance to register
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

    def _find_target(self, event_source: str) -> Optional["StatefulPlugin[Any, Any]"]:
        """Find the component that should handle this mutation.

        Uses O(1) map-based lookup strategy:
        1. Try exact match (for widget-specific instances)
        2. Try component type match (first part before ':')

        Args:
            event_source: Event source string (e.g., "space:MultiAgentSpace:123")

        Returns:
            StatefulPlugin that handles this mutation, or None if not found
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
