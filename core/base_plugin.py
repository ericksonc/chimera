"""BasePlugin - Abstract base for Widgets and Spaces.

This defines the 4 lifecycle hooks that both Widgets and Spaces use to integrate
into the conversation flow:
1. on_user_input - React to user messages (can BLOCK, HALT, or AWAIT_HUMAN)
2. get_instructions - Provide dynamic instructions/ambient context
3. on_agent_output - React to agent responses (can BLOCK, HALT, or AWAIT_HUMAN)
4. get_toolset - Provide a FunctionToolset with tools for the agent

Both Widget and Space inherit from BasePlugin, making them the two primary
extensibility mechanisms in Chimera.
"""

from __future__ import annotations
from abc import ABC
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from pydantic_graph.beta import StepContext
    from .protocols import ReadableThreadState
    from pydantic_ai.agent import AgentRunResult
    from pydantic_ai.toolsets import FunctionToolset
    from .baseplugin import HookResult


class BasePlugin(ABC):
    """Abstract base class for Widgets and Spaces.

    Provides the 4 lifecycle hooks that plugins use to integrate with thread execution:
    - on_user_input: Called when user sends a message
    - get_instructions: Provide dynamic instructions/ambient context for agent
    - on_agent_output: Called when agent produces output
    - get_toolset: Provide a toolset that agent can use

    Hooks can return HookResult to control execution flow (BLOCK, HALT, AWAIT_HUMAN).
    Subclasses override only the hooks they need. Default implementations do nothing.
    """

    async def on_user_input(self, message: str, ctx: 'StepContext') -> Optional['HookResult']:
        """Called when user input arrives (thread_start step).

        Use this to:
        - Process user messages
        - Update plugin state
        - Trigger side effects
        - BLOCK inappropriate messages
        - HALT execution if needed
        - AWAIT_HUMAN for approval

        Args:
            message: The user's message
            ctx: Step context with full thread state and deps

        Returns:
            Optional HookResult to control execution (None = continue)

        Default: Returns None (continue)
        """
        return None

    async def get_instructions(self, state: 'ReadableThreadState') -> str | None:
        """Provide dynamic instructions/ambient context for the agent.

        Called before agent runs (Agent._setup_pai_agent()).
        Return instructions that should be added to the agent's prompt.

        Args:
            state: Read-only view of thread state

        Returns:
            Instructions string, or None if no instructions to provide

        Default: Returns None
        """
        return None

    async def on_agent_output(self, result: 'AgentRunResult', ctx: 'StepContext') -> Optional['HookResult']:
        """Called when agent produces output (turn_complete step).

        Use this to:
        - Process agent responses
        - Update plugin state
        - Trigger side effects
        - BLOCK inappropriate agent actions
        - HALT execution if needed
        - AWAIT_HUMAN for approval

        Args:
            result: AgentRunResult from Pydantic AI
            ctx: Step context with full thread state and deps

        Returns:
            Optional HookResult to control execution (None = continue)

        Default: Returns None (continue)
        """
        return None

    def get_toolset(self) -> Optional['FunctionToolset']:
        """Provide a toolset that the agent can use.

        Called before agent runs (Agent._setup_pai_agent()).
        Return a FunctionToolset containing this plugin's tools.
        The toolset will be registered directly with the PAI agent via agent.toolset().

        Returns:
            FunctionToolset with plugin's tools, or None if no tools

        Default: Returns None

        Example:
            def get_toolset(self) -> FunctionToolset:
                toolset = FunctionToolset()

                @toolset.tool
                def my_tool(arg: str) -> str:
                    return f"Result: {arg}"

                return toolset
        """
        return None
