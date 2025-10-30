"""GenericSpace - Simplest possible space implementation.

This is the default space for single-agent threads. It provides no orchestration,
no multi-agent logic - just a transparent wrapper around one agent.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from core.spaces.base import Space

if TYPE_CHECKING:
    from core.agent import Agent
    from core.threadprotocol.transformer import GenericTransformer


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

    def __init__(self, agent: Agent):
        """Initialize GenericSpace with a single agent.

        Args:
            agent: The agent to wrap (becomes the active agent)
        """
        super().__init__()  # Initialize base Space
        self._agent = agent

    @property
    def active_agent(self) -> Agent:
        """The currently active agent.

        In GenericSpace, there's only one agent, so it's always active.
        Multi-agent spaces will have more complex logic here.
        """
        return self._agent

    def get_transformer(self) -> GenericTransformer:
        """Get the GenericTransformer for simple pass-through transformation.

        GenericSpace uses the simplest transformer - minimal opinions,
        nearly verbatim mapping from ThreadProtocol to ModelMessages.

        Returns:
            Fresh GenericTransformer instance (created per call)
        """
        # Import here to avoid circular dependency
        from core.threadprotocol.transformer import GenericTransformer
        return GenericTransformer()
