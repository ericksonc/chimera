"""Base Space class - Abstract base for all Space implementations.

Spaces are execution environments for agents. They:
1. Manage which agent is active (single or multi-agent orchestration)
2. Have their own lifecycle hooks (as BasePlugin)
3. Manage space-level widgets (shared across all agents)
4. Aggregate plugins for thread.py to call

Thread.py only knows about the Space's BasePlugin interface and ActiveSpace protocol.
It doesn't know about Widgets, Agents, or any concrete types.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Any

from core.base_plugin import BasePlugin

if TYPE_CHECKING:
    from core.agent import Agent
    from core.widget import Widget
    from pydantic_ai.agent import AgentRunResult
    from pydantic_graph.beta import StepContext

# Space configuration type (for BlueprintProtocol)
# Most spaces won't need complex config, but available if needed
SpaceBlueprintT = dict  # Generic dict for now, spaces can override
SpaceMutationT = Any    # Spaces that manage state can define mutation types


class Space(BasePlugin[SpaceBlueprintT, SpaceMutationT], ABC):
    """Abstract base class for all Spaces.

    A Space is both:
    1. A BasePlugin (has lifecycle hooks, can affect execution)
    2. An execution environment (implements ActiveSpace protocol)

    This dual nature allows spaces to:
    - React to user input/agent output (BasePlugin hooks)
    - Orchestrate agent execution (ActiveSpace protocol)
    - Manage space-level widgets (shared across agents)

    Concrete spaces (GenericSpace, GroupChatSpace, etc.) inherit from this.
    """

    def __init__(self):
        """Initialize base space."""
        super().__init__()
        self.widgets: List[Widget] = []  # Space-level widgets (shared)

    # ========================================================================
    # ActiveSpace Protocol Implementation
    # ========================================================================

    @property
    @abstractmethod
    def active_agent(self) -> Agent:
        """The currently active agent.

        Single-agent spaces return their one agent.
        Multi-agent spaces determine this based on orchestration logic.
        """
        raise NotImplementedError()

    async def run_stream(self, ctx: StepContext) -> AgentRunResult:
        """Run the active agent and return result.

        This is the main execution method called by thread.py.
        All spaces use the same pattern:
        1. Get the transformer (space-specific)
        2. Delegate to agent.run_stream()

        Args:
            ctx: Step context with state and deps

        Returns:
            AgentRunResult from Pydantic AI
        """
        # Get transformer (space determines which one)
        transformer = self.get_transformer()

        # Delegate to agent - it handles POV composition and execution
        return await self.active_agent.run_stream(
            ctx=ctx,
            transformer=transformer,
        )

    @abstractmethod
    def get_transformer(self):
        """Get the transformer this space uses for message history.

        Different spaces may use different transformers:
        - GenericSpace: GenericTransformer (pass-through)
        - GroupChatSpace: MultiAgentTransformer (agent name formatting)
        - Custom spaces: Custom transformers

        Returns:
            ThreadProtocolTransformer instance
        """
        raise NotImplementedError()

    # ========================================================================
    # Plugin Aggregation for thread.py
    # ========================================================================

    def get_plugins(self) -> List[BasePlugin]:
        """Get all plugins that should receive lifecycle hooks.

        This aggregates:
        1. The space itself (it's a BasePlugin)
        2. Space-level widgets (shared across agents)
        3. Active agent's widgets (agent-specific)

        Thread.py calls this to get all plugins without knowing
        what they are (could be widgets, spaces, or future plugin types).

        Returns:
            List of BasePlugin instances in execution order
        """
        plugins: List[BasePlugin] = []

        # 1. Space itself gets hooks first (can affect everything)
        plugins.append(self)

        # 2. Space-level widgets (shared state/tools)
        plugins.extend(self.widgets)

        # 3. Active agent's widgets (agent-specific state/tools)
        agent = self.active_agent
        if agent and hasattr(agent, 'widgets'):
            plugins.extend(agent.widgets)

        return plugins

    # ========================================================================
    # Callback Collection (Performance Optimization)
    # ========================================================================

    def get_user_input_callbacks(self) -> List:
        """Get callbacks for plugins that implement on_user_input.

        Only returns callbacks from plugins that have overridden the base method.
        This avoids calling no-op implementations.

        Returns:
            List of on_user_input callables
        """
        callbacks = []
        for plugin in self.get_plugins():
            # Check if plugin overrides the base implementation
            if plugin.on_user_input.__func__ is not BasePlugin.on_user_input:
                callbacks.append(plugin.on_user_input)
        return callbacks

    def get_instructions_providers(self) -> List:
        """Get callbacks for plugins that provide instructions.

        Only returns callbacks from plugins that have overridden get_instructions.

        Returns:
            List of get_instructions callables
        """
        callbacks = []
        for plugin in self.get_plugins():
            # Check if plugin overrides the base implementation
            if plugin.get_instructions.__func__ is not BasePlugin.get_instructions:
                callbacks.append(plugin.get_instructions)
        return callbacks

    def get_toolset_providers(self) -> List:
        """Get callbacks for plugins that provide toolsets.

        Only returns callbacks from plugins that have overridden get_toolset.

        Returns:
            List of get_toolset callables
        """
        callbacks = []
        for plugin in self.get_plugins():
            # Check if plugin overrides the base implementation
            if plugin.get_toolset.__func__ is not BasePlugin.get_toolset:
                callbacks.append(plugin.get_toolset)
        return callbacks

    def get_agent_output_callbacks(self) -> List:
        """Get callbacks for plugins that process agent output.

        Only returns callbacks from plugins that have overridden on_agent_output.

        Returns:
            List of on_agent_output callables
        """
        callbacks = []
        for plugin in self.get_plugins():
            # Check if plugin overrides the base implementation
            if plugin.on_agent_output.__func__ is not BasePlugin.on_agent_output:
                callbacks.append(plugin.on_agent_output)
        return callbacks

    def register_widget(self, widget: Widget) -> None:
        """Register a space-level widget.

        Space-level widgets are shared across all agents in the space.
        Their state mutations affect all agents.

        Args:
            widget: Widget to register at space level
        """
        if widget not in self.widgets:
            self.widgets.append(widget)

    # ========================================================================
    # Space-level lifecycle hooks (inherited from BasePlugin)
    # ========================================================================

    # Spaces can override these BasePlugin hooks to:
    # - Validate user input at space level
    # - Add space-level instructions (like agent list in group chat)
    # - React to agent output (e.g., determine next agent)
    # - Provide space-level tools (e.g., spawn_thread)

    # Default implementations from BasePlugin return None (no-op)