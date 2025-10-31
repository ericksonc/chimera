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
from typing import TYPE_CHECKING, List

from core.base_plugin import BasePlugin

if TYPE_CHECKING:
    from core.agent import Agent
    from core.widget import Widget
    from pydantic_ai.agent import AgentRunResult
    from pydantic_graph.beta import StepContext
    from core.threadprotocol.blueprint import ComponentConfig, AgentConfig, SpaceConfig


class Space(BasePlugin, ABC):
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
        self._agents: List[Agent] = []  # Agents in this space
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
    # BlueprintProtocol Serialization
    # ========================================================================

    @classmethod
    def from_blueprint_config(cls, config: 'ComponentConfig', space_config: 'SpaceConfig') -> 'Space':
        """Deserialize Space from BlueprintProtocol format.

        This base implementation handles agent resolution (inline vs referenced)
        which is common to all spaces. Subclasses can override to add custom
        deserialization logic if they have custom config.

        Args:
            config: ComponentConfig for the space (may contain custom config)
            space_config: SpaceConfig from BlueprintProtocol (contains agents)

        Returns:
            Space instance with resolved agents
        """
        # Resolve agents using helper (handles inline/referenced)
        agents = cls._resolve_agents_from_config(space_config)

        # Create space instance (no-arg constructor)
        space = cls()

        # Set resolved agents
        space._agents = agents

        # Set instance_id
        space.instance_id = config.instance_id

        return space

    def to_blueprint_config(self) -> 'ComponentConfig':
        """Serialize Space to BlueprintProtocol format.

        Default implementation returns minimal config. Spaces with custom
        configuration should override this and include their config data.

        Returns:
            ComponentConfig with space metadata
        """
        from core.threadprotocol.blueprint import ComponentConfig

        return ComponentConfig(
            class_name=f"core.spaces.{self.__class__.__name__}",
            version="1.0.0",
            instance_id=self.instance_id or "space",
            config={}  # No custom config by default - agents handled at space level
        )

    @classmethod
    def _resolve_agents_from_config(cls, space_config: 'SpaceConfig') -> List['Agent']:
        """Resolve agents from SpaceConfig (inline or referenced).

        This is a helper method for subclasses to use in their from_blueprint_config()
        implementation. It handles both inline and referenced agent configs.

        Args:
            space_config: SpaceConfig containing agent definitions

        Returns:
            List of resolved Agent instances
        """
        from uuid import UUID
        from core.agent import Agent
        from core.threadprotocol.blueprint import InlineAgentConfig, ReferencedAgentConfig

        agents = []
        for agent_config in space_config.agents:
            if isinstance(agent_config, InlineAgentConfig):
                # Create agent from inline config
                agent = Agent(
                    id=UUID(agent_config.id),
                    name=agent_config.name,
                    description=agent_config.description,
                    base_prompt=agent_config.base_prompt,
                    model_string=agent_config.model_string
                )
                # TODO: Reconstruct agent widgets using Widget.from_blueprint_config
                # for widget_config in agent_config.widgets:
                #     widget = load_widget_class(widget_config.class_name).from_blueprint_config(widget_config)
                #     agent.register_widget(widget)
                agents.append(agent)
            elif isinstance(agent_config, ReferencedAgentConfig):
                # Referenced agents loaded from registry
                # TODO: Implement agent registry loading via Agent.from_yaml()
                raise NotImplementedError("Referenced agents not yet implemented")
            else:
                raise ValueError(f"Unknown agent config type: {type(agent_config)}")

        return agents

    # ========================================================================
    # Blueprint Generation
    # ========================================================================

    def serialize_blueprint_json(self, output_path: str, thread_id: str | None = None) -> None:
        """Generate complete Blueprint and save as JSON.

        This is the main entry point for blueprint generation. It:
        1. Serializes all agents (with their widgets)
        2. Serializes the space (with space-level widgets)
        3. Creates the Blueprint object
        4. Writes to JSON file

        Args:
            output_path: Path to save JSON file (e.g., "blueprints/my_blueprint.json")
            thread_id: Optional thread ID (generates one if not provided)
        """
        import json
        from uuid import uuid4
        from core.threadprotocol.blueprint import Blueprint, ReferencedSpaceConfig

        # Generate thread ID if not provided
        if thread_id is None:
            thread_id = str(uuid4())

        # Serialize all agents
        agent_configs = []
        for agent in self._get_all_agents():
            agent_config = agent.to_blueprint_config()
            agent_configs.append(agent_config)

        # Serialize space
        space_component_config = self.to_blueprint_config()

        # Create space config (ReferencedSpaceConfig for custom spaces)
        # Agents are nested under space now
        space_config = ReferencedSpaceConfig(
            class_name=space_component_config.class_name,
            version=space_component_config.version,
            agents=agent_configs,  # Nest agents under space
            config=space_component_config.config,
            widgets=[w.to_blueprint_config() for w in self.widgets]
        )

        # Create blueprint (agents are now nested in space_config)
        blueprint = Blueprint(
            thread_id=thread_id,
            space=space_config
        )

        # Convert to event dict and write as JSON
        event_dict = blueprint.to_event()

        with open(output_path, 'w') as f:
            json.dump(event_dict, f, indent=2)

        print(f"Blueprint saved to: {output_path}")

    @abstractmethod
    def _get_all_agents(self) -> List['Agent']:
        """Get all agents in this space.

        Single-agent spaces return [self.active_agent].
        Multi-agent spaces return all agents.

        Returns:
            List of Agent instances
        """
        raise NotImplementedError()

    # ========================================================================
    # Space-level lifecycle hooks (inherited from BasePlugin)
    # ========================================================================

    # Spaces can override these BasePlugin hooks to:
    # - Validate user input at space level
    # - Add space-level instructions (like agent list in group chat)
    # - React to agent output (e.g., determine next agent)
    # - Provide space-level tools (e.g., spawn_thread)

    # Default implementations from BasePlugin return None (no-op)