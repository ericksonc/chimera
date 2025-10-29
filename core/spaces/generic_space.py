"""GenericSpace - Simplest possible space implementation.

This is the default space for single-agent threads. It provides no orchestration,
no multi-agent logic - just a transparent wrapper around one agent.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import Agent
    from core.protocols import ReadableThreadState
    from core.threadprotocol.transformer import GenericTransformer
    from pydantic_ai.agent import AgentRunResult


class GenericSpace:
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
        self._agent = agent

    @property
    def active_agent(self) -> Agent:
        """The currently active agent.

        In GenericSpace, there's only one agent, so it's always active.
        Multi-agent spaces will have more complex logic here.
        """
        return self._agent

    async def run_stream(self, ctx) -> AgentRunResult:
        """Run the active agent and return result.

        This delegates to Agent.run_stream() with a GenericTransformer.
        The transformer is instantiated per-call (not cached).

        Args:
            ctx: Step context with state and deps (from pydantic-graph beta API)

        Returns:
            AgentRunResult from Pydantic AI

        The agent is responsible for:
        - Transforming message history via the transformer
        - Composing its POV (tools, widgets, ambient context)
        - Running PAI agent.iter()
        - Returning the result
        """
        # Import here to avoid circular dependency
        from core.threadprotocol.transformer import GenericTransformer

        # Create transformer per-call (space defines which transformer to use)
        transformer = GenericTransformer()

        # Delegate to agent - it handles the heavy lifting
        return await self._agent.run_stream(
            ctx=ctx,
            transformer=transformer,
        )
