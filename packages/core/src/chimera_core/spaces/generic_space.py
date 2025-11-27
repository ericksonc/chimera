"""GenericSpace - Simplest possible space implementation.

This is the default space for single-agent threads. It provides no orchestration,
no multi-agent logic - just a transparent wrapper around one agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chimera_core.spaces.base import Space

if TYPE_CHECKING:
    from chimera_core.agent import Agent
    from chimera_core.threadprotocol.transformer import GenericTransformer


class GenericSpace(Space):
    """Simplest possible space - single agent, generic transformation.

    GenericSpace is the default space used in BlueprintProtocol when no
    space is explicitly specified. It:
    - Wraps exactly one agent (no multi-agent orchestration)
    - Uses GenericTransformer (minimal, pass-through message transformation)
    - Has no state beyond the wrapped agent
    - Implements ActiveSpace protocol for thread.py integration

    This is the starting point. Future spaces (GroupChatSpace, etc.) will
    add orchestration patterns, custom transformers, and multi-agent logic.
    """

    def __init__(self, agent: Agent = None):
        """Initialize GenericSpace with a single agent.

        Args:
            agent: Optional agent to wrap (for programmatic creation).
                   If None, agents should be set via from_blueprint_config().
        """
        super().__init__()  # Initialize base Space
        if agent:
            self._agents = [agent]

    @property
    def active_agent(self) -> Agent:
        """The currently active agent.

        In GenericSpace, there's only one agent, so it's always active.
        Multi-agent spaces will have more complex logic here.

        Raises:
            ValueError: If no agents or multiple agents configured
        """
        if not self._agents:
            raise ValueError("GenericSpace has no agents configured")
        if len(self._agents) != 1:
            raise ValueError(f"GenericSpace requires exactly 1 agent, has {len(self._agents)}")
        return self._agents[0]

    def _get_all_agents(self):
        """Get all agents in this space.

        GenericSpace only has one agent.

        Returns:
            List containing the single agent
        """
        return self._agents

    def get_transformer(self) -> GenericTransformer:
        """Get the GenericTransformer for simple pass-through transformation.

        GenericSpace uses the simplest transformer - minimal opinions,
        nearly verbatim mapping from ThreadProtocol to ModelMessages.

        Returns:
            Fresh GenericTransformer instance (created per call)
        """
        # Import here to avoid circular dependency
        from chimera_core.threadprotocol.transformer import GenericTransformer

        return GenericTransformer()
