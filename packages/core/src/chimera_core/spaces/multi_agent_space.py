"""MultiAgentSpace - Abstract base for spaces with mutable active agent.

This provides the foundation for multi-agent orchestration spaces like:
- RosterSpace (tool-based agent switching)
- GroupChatSpace (structured output-based routing)
- RoundRobinSpace (automatic rotation)

All multi-agent spaces share:
1. Mutable active_agent state (via StatefulPlugin)
2. Agent selection mutations
3. BaseMultiAgentTransformer for message formatting
"""

from __future__ import annotations

import logging
from abc import ABC
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Optional

from chimera_core.base_plugin import StatefulPlugin
from chimera_core.spaces.base import Space

# Configure logger
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pydantic_graph.beta import StepContext

    from chimera_core.agent import Agent
    from chimera_core.protocols import ReadableThreadState
    from chimera_core.threadprotocol.blueprint import ComponentConfig, SpaceConfig
    from chimera_core.threadprotocol.multi_agent_transformer import BaseMultiAgentTransformer


# ============================================================================
# Multi-Agent Mutation Types
# ============================================================================


@dataclass
class AgentSelectionMutation:
    """Mutation for changing the active agent.

    All MultiAgentSpaces emit this mutation type when switching agents.
    The trigger (tool call, structured output, automatic, etc.) varies by space.
    """

    new_agent_identifier: str  # Thread-scoped identifier, not UUID
    reason: str  # "tool_call", "round_complete", "structured_output", etc.
    metadata: dict = field(default_factory=dict)  # Space-specific context


@dataclass
class MultiAgentSpaceConfig:
    """Configuration for MultiAgentSpace initialization.

    This is the SpaceBlueprintT for multi-agent spaces.
    """

    initial_agent_identifier: str  # Which agent starts active


# ============================================================================
# MultiAgentSpace ABC
# ============================================================================


class MultiAgentSpace(Space, StatefulPlugin[MultiAgentSpaceConfig, AgentSelectionMutation], ABC):
    """Abstract base for all multi-agent spaces.

    Provides:
    - Mutable active_agent state via StatefulPlugin
    - Agent selection mutations
    - BaseMultiAgentTransformer integration
    - Common multi-agent orchestration infrastructure

    Subclasses implement:
    - How agent selection is triggered (tools, structured output, automatic, etc.)
    - Custom get_toolset() if needed
    - Custom get_instructions() for agent roster display
    """

    def __init__(self):
        """Initialize multi-agent space."""
        super().__init__()
        self._active_agent_identifier: Optional[str] = None
        self._emit_threadprotocol_event = None  # Captured from ctx in get_toolset
        self._event_loop = None  # Captured from ctx in get_toolset (for thread-safe async calls)

    # ========================================================================
    # ActiveSpace Protocol - Active Agent Management
    # ========================================================================

    @property
    def active_agent(self) -> "Agent":
        """Return the currently active agent.

        Uses _active_agent_identifier to lookup from roster.

        Returns:
            Currently active Agent instance

        Raises:
            ValueError: If no active agent is set or identifier not found
        """
        if not self._active_agent_identifier:
            raise ValueError("No active agent set in MultiAgentSpace")

        return self._get_agent_by_identifier(self._active_agent_identifier)

    # ========================================================================
    # StatefulPlugin Implementation - Mutation Management
    # ========================================================================

    def save_mutation(self, mutation: AgentSelectionMutation) -> None:
        """Save agent selection mutation to ThreadProtocol.

        v0.0.7: Writes a data-app-chimera event with nested structure:
        {
            "type": "data-app-chimera",
            "data": {
                "source": "space:MultiAgentSpace:{instance_id}",
                "payload": {mutation serialized to dict}
            }
        }

        Args:
            mutation: The agent selection mutation to save
        """
        logger.info(f"[MUTATION SAVE] Called with mutation: {asdict(mutation)}")
        logger.info(f"[MUTATION SAVE] _emit_threadprotocol_event={self._emit_threadprotocol_event}")

        if not self._emit_threadprotocol_event:
            # No emit function available - this can happen during initialization
            # or when mutations are created outside of an active thread
            logger.warning("[MUTATION SAVE] No emit function available - mutation will be DROPPED!")
            logger.warning("[MUTATION SAVE] This means agent switching won't work!")
            return

        # Create mutation payload (v0.0.7: goes inside data.payload)
        mutation_payload = {
            "newAgentIdentifier": mutation.new_agent_identifier,
            "reason": mutation.reason,
            "metadata": mutation.metadata,
        }

        # Build event source for routing (v0.0.7: goes inside data.source)
        event_source = f"space:MultiAgentSpace:{self.instance_id or 'unknown'}"

        logger.info(
            f"[MUTATION SAVE] Attempting to emit event: source={event_source}, payload={mutation_payload}"
        )

        # Emit the mutation event
        # Note: This is a sync function but emit is async
        # Tools run in worker threads, so we use run_coroutine_threadsafe
        import asyncio

        try:
            # Create the event (v0.0.7: nested data structure)
            event = {
                "type": "data-app-chimera",
                "data": {"source": event_source, "payload": mutation_payload},
            }

            logger.info(f"[MUTATION SAVE] Calling emit_threadprotocol_event with: {event}")

            if not self._event_loop:
                logger.error(
                    "[MUTATION SAVE] No event loop captured! Cannot emit from worker thread."
                )
                return

            # Use run_coroutine_threadsafe to schedule the async call from worker thread
            asyncio.run_coroutine_threadsafe(
                self._emit_threadprotocol_event(event), self._event_loop
            )
            # Don't wait for completion - fire and forget
            # The event will be emitted asynchronously

            logger.info("[MUTATION SAVE] Successfully scheduled mutation event emission")
        except Exception as e:
            logger.error(f"[MUTATION SAVE] Failed to emit mutation: {e}", exc_info=True)

    def apply_mutation(self, mutation: AgentSelectionMutation | dict) -> None:
        """Apply agent selection mutation to local state.

        This updates the active agent identifier.
        This must be deterministic and idempotent.

        Args:
            mutation: The mutation to apply (typed or dict from ThreadProtocol)
        """
        # Handle dict input from ThreadProtocol replay (v0.0.6 camelCase)
        if isinstance(mutation, dict):
            # Convert camelCase to snake_case for dataclass
            mutation = AgentSelectionMutation(
                new_agent_identifier=mutation["newAgentIdentifier"],
                reason=mutation["reason"],
                metadata=mutation.get("metadata", {}),
            )

        logger.info(f"[MUTATION APPLY] Called with mutation: {asdict(mutation)}")
        logger.info(f"[MUTATION APPLY] Current active agent: {self._active_agent_identifier}")

        # Validate the new identifier exists
        try:
            new_agent = self._get_agent_by_identifier(mutation.new_agent_identifier)
            logger.info(
                f"[MUTATION APPLY] Validated - switching to agent: {new_agent.name} ({mutation.new_agent_identifier})"
            )
        except ValueError as e:
            logger.error(f"[MUTATION APPLY] Validation failed: {e}")
            raise ValueError(f"Cannot switch to agent: {e}")

        # Update active agent
        old_identifier = self._active_agent_identifier
        self._active_agent_identifier = mutation.new_agent_identifier
        logger.info(
            f"[MUTATION APPLY] Agent switched: {old_identifier} -> {self._active_agent_identifier}"
        )

    # ========================================================================
    # Transformer - Multi-Agent Message Formatting
    # ========================================================================

    def _get_event_source(self) -> str:
        """Build event_source for MultiAgentSpace mutations.

        All MultiAgentSpace subclasses use "MultiAgentSpace" as the class name
        since they share the same mutation schema (AgentSelectionMutation).

        Returns:
            Event source: "space:MultiAgentSpace:{instance_id}"
        """
        return f"space:MultiAgentSpace:{self.instance_id or 'unknown'}"

    @property
    def event_source_prefix(self) -> str:
        """Routing prefix for state reconstruction.

        All space mutations route to the active space, so we use the component
        type "space" as the prefix for O(1) lookup in StateReconstructor.

        Returns:
            "space" (matches any "space:*" event source)
        """
        return "space"

    def get_transformer(self) -> "BaseMultiAgentTransformer":
        """Get the BaseMultiAgentTransformer for multi-agent message formatting.

        All MultiAgentSpaces use BaseMultiAgentTransformer which provides:
        - Agent name prefixes
        - Tool call visibility (own vs others)
        - Failed tool call filtering

        Returns:
            BaseMultiAgentTransformer instance configured with this space's agents
        """
        from chimera_core.threadprotocol.multi_agent_transformer import BaseMultiAgentTransformer

        # Build agents_by_identifier dict for transformer (using string identifiers, not UUIDs)
        agents_by_identifier = {agent.identifier: agent for agent in self._agents}

        return BaseMultiAgentTransformer(agents_by_identifier=agents_by_identifier)

    # ========================================================================
    # Initialization from BlueprintProtocol
    # ========================================================================

    @classmethod
    def from_blueprint_config(cls, space_config: "SpaceConfig") -> "MultiAgentSpace":
        """Deserialize MultiAgentSpace from BlueprintProtocol format.

        This extends Space.from_blueprint_config() to also set the initial active agent.

        Args:
            space_config: SpaceConfig from BlueprintProtocol (contains all space data)

        Returns:
            MultiAgentSpace instance with resolved agents and set active agent
        """
        # Use parent implementation for agent resolution and validation
        space = super().from_blueprint_config(space_config)

        # Extract multi-agent config from space_config
        if hasattr(space_config, "config") and space_config.config:
            initial_agent_id = space_config.config.get("initial_agent_identifier")
            if initial_agent_id:
                # Set the initial active agent
                space._active_agent_identifier = initial_agent_id

        return space

    def to_blueprint_config(self) -> "ComponentConfig":
        """Serialize MultiAgentSpace to BlueprintProtocol format.

        Includes the current active agent as initial_agent_identifier.

        Returns:
            ComponentConfig with MultiAgentSpaceConfig
        """
        from chimera_core.threadprotocol.blueprint import ComponentConfig

        return ComponentConfig(
            class_name=f"chimera_core.spaces.{self.__class__.__name__}",
            version="1.0.0",
            instance_id=self.instance_id or "multi_agent_space",
            config={"initial_agent_identifier": self._active_agent_identifier},
        )

    # NOTE: emit_threadprotocol_event is now captured in get_toolset(ctx)
    # No need for separate injection - the emit function comes from ctx.deps

    # ========================================================================
    # Default Ambient Context - Agent Roster Display
    # ========================================================================

    async def get_instructions(self, ctx: "StepContext") -> str:
        """Provide agent roster as ambient context.

        This default implementation shows all available agents with:
        - identifier
        - name
        - description
        - current status

        Subclasses can override to customize the roster display.

        Args:
            ctx: Step context with state and deps

        Returns:
            Formatted agent roster string
        """

        # Only show OTHER agents, not the current one
        other_agents = [
            agent for agent in self._agents if agent.identifier != self._active_agent_identifier
        ]

        if not other_agents:
            return ""  # No other agents to show

        roster_lines = []
        for agent in other_agents:
            roster_lines.append(f"- {agent.identifier}: {agent.name} - {agent.description}")

        roster = "\n".join(roster_lines)
        return f"""# LIST OF OTHER AGENTS

{roster}"""
