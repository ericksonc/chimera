"""BasePlugin - Abstract base for Widgets and Spaces.

This defines the 4 lifecycle hooks that both Widgets and Spaces use to integrate
into the conversation flow:
1. on_user_input - React to user messages (can BLOCK, HALT, or AWAIT_HUMAN)
2. get_instructions - Provide dynamic instructions/ambient context
3. on_agent_output - React to agent responses (can BLOCK, HALT, or AWAIT_HUMAN)
4. get_toolset - Provide a FunctionToolset with tools for the agent

Both Widget and Space inherit from BasePlugin, making them the two primary
extensibility mechanisms in Chimera.

For stateful plugins (widgets/spaces with state), the mutation pattern ensures
replayability:
1. Create mutation describing state change
2. Save to ThreadProtocol via save_mutation()
3. Apply to local state via apply_mutation()

The mutate() helper enforces this order: mutations is mutations is mutations.
"""

from __future__ import annotations

import re
from abc import ABC, ABCMeta, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult
    from pydantic_ai.toolsets import FunctionToolset
    from pydantic_graph.beta import StepContext

    from .protocols import ReadableThreadState
    from .threadprotocol.blueprint import ComponentConfig


# ============================================================================
# Execution Control
# ============================================================================


class ExecutionControl(Enum):
    """Control flow signals for hook results."""

    CONTINUE = "continue"
    BLOCK_ACTION = "block_action"
    HALT = "halt"
    AWAIT_HUMAN = "await_human"


# ============================================================================
# Type Variables
# ============================================================================

BlueprintT = TypeVar("BlueprintT")  # Turn 0 configuration type
MutationT = TypeVar("MutationT")  # Runtime state mutation type


# ============================================================================
# Plugin Metaclass - Auto-capture class metadata
# ============================================================================


class PluginMeta(ABCMeta):
    """Metaclass that automatically captures class metadata for plugins.

    This metaclass runs at class definition time and:
    1. Auto-captures the full Python class path (module + class name)
    2. Sets it as component_class_name if not manually overridden
    3. Auto-registers Widget subclasses to the widget registry
    4. Validates that component_version is set (must be explicit)

    This eliminates the need for manual component_class_name definitions
    and manual widget registration, making widgets more concise.

    Example:
        class QAWidget(Widget[QAWidgetConfig]):
            component_version = "1.0.0"  # Required
            # component_class_name auto-generated as "core.widgets.qa_widget.QAWidget"
            # Widget auto-registered (no register_widget() call needed)
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        """Create class and auto-capture metadata."""
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Skip abstract base classes (BasePlugin, Widget, Space, StatefulPlugin, etc.)
        if namespace.get("__module__") == "chimera_core.base_plugin":
            return cls
        if namespace.get("__module__") == "chimera_core.widget":
            return cls
        if namespace.get("__module__") == "chimera_core.spaces.base":
            return cls

        # Auto-capture class path ONLY if not manually set
        # This preserves backwards compatibility during migration
        if "component_class_name" not in namespace:
            module = cls.__module__
            class_name = cls.__name__
            cls.component_class_name = f"{module}.{class_name}"

        # Auto-register Widget subclasses
        # Check if this is a concrete Widget class (not an abstract base)
        # We determine this by checking if it inherits from a Widget base
        # and is not itself an abstract base class
        mcs._auto_register_widget(cls, namespace)

        return cls

    @staticmethod
    def _auto_register_widget(cls, namespace):
        """Auto-register Widget subclasses to the widget registry.

        Only registers concrete widget classes that:
        1. Inherit from Widget (check bases)
        2. Are not abstract (no abstract methods)
        3. Have a component_class_name set

        Uses late import to avoid circular dependencies.
        """
        # Check if this class has Widget in its MRO (but isn't Widget itself)
        # We need to check the string name to avoid import issues
        is_widget_subclass = False
        for base in cls.__mro__[1:]:  # Skip self, check parents
            base_module = getattr(base, "__module__", "")
            base_name = getattr(base, "__name__", "")
            # Check if this is the Widget or StatefulWidget class
            if base_module == "chimera_core.widget" and base_name in ("Widget", "StatefulWidget"):
                is_widget_subclass = True
                break

        if not is_widget_subclass:
            return  # Not a widget, skip registration

        # Skip if this is an abstract class (has abstract methods)
        if getattr(cls, "__abstractmethods__", None):
            return  # Abstract class, skip registration

        # Get the auto-generated class name
        class_name = getattr(cls, "component_class_name", None)
        if not class_name:
            return  # No class name, skip registration

        # Late import to avoid circular dependencies
        try:
            from .widget_registry import register_widget

            register_widget(class_name, cls)
        except ImportError:
            # Registry not available yet (likely during initial module loading)
            # This is okay - widgets will be registered when imported after registry exists
            pass


# ============================================================================
# Hook Result
# ============================================================================


class HookResult(Generic[MutationT]):
    """Result returned from lifecycle hooks to control execution flow.

    Hooks can return HookResult to:
    - Control execution (CONTINUE, BLOCK, HALT, AWAIT_HUMAN)
    - Provide feedback to agent/user
    - Register state mutations

    Example:
        # Block with reason
        return HookResult.block("Message contains inappropriate content")

        # Continue with mutations
        return HookResult.continue_with(mutations=[my_mutation])

        # Halt execution
        return HookResult.halt("Critical error detected")
    """

    def __init__(self, control: ExecutionControl = ExecutionControl.CONTINUE):
        self.control = control
        self.agent_message: str | None = None  # Message for agent to see
        self.user_message: str | None = None  # Message for user to see
        self.mutations: list[MutationT] = []

    @classmethod
    def continue_with(
        cls, mutations: list[MutationT] | MutationT | None = None
    ) -> "HookResult[MutationT]":
        """Continue normally, optionally with state mutations."""
        result = cls(ExecutionControl.CONTINUE)
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def block(
        cls,
        reason: str,
        user_msg: str | None = None,
        mutations: list[MutationT] | MutationT | None = None,
    ) -> "HookResult[MutationT]":
        """Block this specific action but continue execution."""
        result = cls(ExecutionControl.BLOCK_ACTION)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def halt(
        cls,
        reason: str,
        user_msg: str | None = None,
        mutations: list[MutationT] | MutationT | None = None,
    ) -> "HookResult[MutationT]":
        """Halt the entire process permanently."""
        result = cls(ExecutionControl.HALT)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def await_human(
        cls, prompt: str, mutations: list[MutationT] | MutationT | None = None
    ) -> "HookResult[MutationT]":
        """Pause execution and wait for human approval."""
        result = cls(ExecutionControl.AWAIT_HUMAN)
        result.agent_message = "Waiting for human input..."
        result.user_message = prompt
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result


# ============================================================================
# BasePlugin
# ============================================================================


class BasePlugin(Generic[BlueprintT], ABC, metaclass=PluginMeta):
    """Abstract base class for Widgets and Spaces (stateless plugins).

    Provides the 4 lifecycle hooks that plugins use to integrate with thread execution:
    - on_user_input: Called when user sends a message
    - get_instructions: Provide dynamic instructions/ambient context for agent
    - on_agent_output: Called when agent produces output
    - get_toolset: Provide a toolset that agent can use

    Hooks can return HookResult to control execution flow (BLOCK, HALT, AWAIT_HUMAN).
    Subclasses override only the hooks they need. Default implementations do nothing.

    Type parameters:
    - BlueprintT: Configuration type stored in BlueprintProtocol (Turn 0 config)

    For plugins that need state mutations, use StatefulPlugin subclass instead.

    **Auto-Registration (NEW):**
    The PluginMeta metaclass automatically captures component_class_name from
    the module path and class name. Subclasses only need to set component_version.

    Example:
        class ContextDocsWidget(BasePlugin[ContextDocsConfig]):
            component_version = "1.0.0"  # Required - explicit versioning
            # component_class_name auto-generated as "core.widgets.ContextDocsWidget"
    """

    # Component metadata
    component_class_name: str = None  # Auto-generated by PluginMeta (or manually override)
    component_version: str = None  # REQUIRED - must be set by subclasses
    instance_id: str = None  # Set during registration

    @property
    @abstractmethod
    def component_type(self) -> str:
        """Component type for event sources: 'space', 'widget', or 'plugin'.

        This property identifies what kind of component this is for mutation routing.
        Subclasses must override this to return their component type.

        Returns:
            Component type string ('space', 'widget', or 'plugin')
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement component_type property"
        )

    async def on_user_input(self, message: str, ctx: "StepContext") -> Optional["HookResult[Any]"]:
        """Called when user input arrives (thread_start step).

        Use this to:
        - Process user messages
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

    async def get_instructions(self, ctx: "StepContext") -> str | None:
        """Provide dynamic instructions/ambient context for the agent.

        Called before agent runs (Agent._setup_pai_agent()).
        Return instructions that should be added to the agent's prompt.

        Args:
            ctx: Step context with state and deps (access state via ctx.state,
                 client_context via ctx.deps.client_context)

        Returns:
            Instructions string, or None if no instructions to provide

        Default: Returns None
        """
        return None

    async def on_agent_output(
        self, result: "AgentRunResult", ctx: "StepContext"
    ) -> Optional["HookResult[Any]"]:
        """Called when agent produces output (turn_complete step).

        Use this to:
        - Process agent responses
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

    def get_toolset(self, ctx: "StepContext") -> Optional["FunctionToolset"]:
        """Provide a toolset that the agent can use.

        Called before agent runs (Agent._setup_pai_agent()).
        Return a FunctionToolset containing this plugin's tools.
        The toolset will be registered directly with the PAI agent via agent.toolset().

        Args:
            ctx: Step context with state and deps (for accessing emit functions, etc.)

        Returns:
            FunctionToolset with plugin's tools, or None if no tools

        Default: Returns None

        Example:
            def get_toolset(self, ctx) -> FunctionToolset:
                toolset = FunctionToolset()

                @toolset.tool
                def my_tool(arg: str) -> str:
                    # Can access ctx.deps here via closure
                    return f"Result: {arg}"

                return toolset
        """
        return None

    # ========================================================================
    # BlueprintProtocol Serialization
    # ========================================================================

    @classmethod
    def _default_instance_id(cls) -> str:
        """Generate default instance ID from class name.

        Converts class name to snake_case and appends "_inst1".
        Example: QAWidget → "qa_widget_inst1"

        Returns:
            Default instance ID string
        """
        name = cls.__name__
        # Convert CamelCase to snake_case
        snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        return f"{snake_case}_inst1"

    def _serialize_config(self) -> dict:
        """Serialize component-specific configuration to dict.

        Subclasses should override this to return their config as a JSON-serializable dict.
        The default implementation returns an empty dict (for components with no config).

        Returns:
            Configuration dict (JSON-serializable)

        Example:
            def _serialize_config(self) -> dict:
                return {
                    "enabled": self.enabled,
                    "max_items": self.max_items
                }
        """
        return {}  # Default: no config

    def to_blueprint_config(self) -> "ComponentConfig[BlueprintT]":
        """Serialize this component instance to BlueprintProtocol format.

        This default implementation handles the boilerplate (class_name, version, instance_id).
        Subclasses only need to override _serialize_config() to provide their config dict.

        For components with complex serialization needs, this method can still be overridden.

        Returns:
            ComponentConfig[BlueprintT]: Typed component configuration

        Example (simple - just override _serialize_config):
            def _serialize_config(self) -> dict:
                return {"enabled": self.enabled}

        Example (complex - override entire method):
            def to_blueprint_config(self) -> ComponentConfig:
                # Custom serialization logic
                return ComponentConfig(...)
        """
        from .threadprotocol.blueprint import ComponentConfig

        return ComponentConfig(
            class_name=self.component_class_name,
            version=self.component_version,
            instance_id=self.instance_id or self._default_instance_id(),
            config=self._serialize_config(),
        )

    if TYPE_CHECKING:
        from chimera_core.agent import Agent

    @classmethod
    @abstractmethod
    def from_blueprint_config(
        cls, config: "ComponentConfig[BlueprintT]", agent: "Agent"
    ) -> "BasePlugin[BlueprintT, MutationT]":
        """Deserialize component instance from BlueprintProtocol format.

        Creates a new component instance from stored configuration.

        Args:
            config: Typed ComponentConfig with component-specific config
            agent: Agent instance that owns this widget (for agent-level widgets)

        Returns:
            Component instance

        Example:
            @classmethod
            def from_blueprint_config(cls, config: ComponentConfig[TodoConfig], agent: Agent) -> TodoWidget:
                widget = cls()
                widget.instance_id = config.instance_id
                widget.todos = config.config.initial_todos
                return widget
        """
        raise NotImplementedError(f"{cls.__name__} must implement from_blueprint_config()")


# ============================================================================
# StatefulPlugin - For plugins with mutable state
# ============================================================================


class StatefulPlugin(BasePlugin[BlueprintT], Generic[BlueprintT, MutationT], ABC):
    """Abstract base class for plugins with mutable state.

    Extends BasePlugin to add mutation pattern for state management.
    Stateful plugins MUST:
    1. Define both type parameters: class TodoWidget(StatefulPlugin[TodoConfig, TodoMutation])
    2. Implement save_mutation() abstract method to persist to ThreadProtocol
    3. Implement apply_mutation() abstract method to update local state
    4. Use mutate() to change state (never mutate directly)

    The mutation pattern ensures:
    - Runtime state matches ThreadProtocol
    - Thread replay produces identical state
    - State changes are auditable

    Mutations are automatically applied during turn_start via the on_turn_start hook.
    Each StatefulPlugin scans ThreadProtocol events for mutations targeting itself
    and applies them to synchronize state.

    Example:
        @dataclass
        class TodoConfig:
            initial_todos: list[str]

        @dataclass
        class TodoMutation:
            action: Literal["add", "remove", "toggle"]
            todo_id: str
            text: str | None = None

        class TodoWidget(StatefulPlugin[TodoConfig, TodoMutation]):
            def __init__(self):
                super().__init__()
                self.todos: list[str] = []

            def save_mutation(self, mutation: TodoMutation) -> None:
                # Write to ThreadProtocol
                # TODO: Get writer from context
                pass

            def apply_mutation(self, mutation: TodoMutation | dict) -> None:
                # Handle dict input (from ThreadProtocol replay)
                if isinstance(mutation, dict):
                    mutation = TodoMutation(**mutation)

                if mutation.action == "add":
                    self.todos.append(mutation.text)
                elif mutation.action == "remove":
                    self.todos.remove(mutation.text)
    """

    def mutate(self, mutation: MutationT) -> None:
        """Mutate plugin state via ThreadProtocol.

        This is the ONLY way to change plugin state:
        1. Save mutation to ThreadProtocol (persistence)
        2. Apply mutation to local state (runtime)

        Args:
            mutation: Typed mutation describing state change

        Example:
            def add_todo(self, text: str):
                mutation = TodoMutation(action="add", todo_id=new_id, text=text)
                self.mutate(mutation)  # Saves then applies
        """
        self.save_mutation(mutation)  # 1. Persist to ThreadProtocol
        self.apply_mutation(mutation)  # 2. Apply to local state

    async def on_turn_start(self, ctx: "StepContext") -> Optional["HookResult[Any]"]:
        """Apply mutations from ThreadProtocol history during turn setup.

        Uses cached mutation index from ThreadState for O(1) lookup instead of
        O(n) event scanning. This ensures plugin state is synchronized with
        conversation history before the agent runs.

        Performance optimization (Phase 3):
        - OLD: O(n events) scan per plugin = O(n × m plugins)
        - NEW: O(1) index lookup per plugin = O(n + m)
        - Example: 1000 events × 10 plugins: 10,000 → 1,010 operations

        v0.0.7: Reads from data.source and data.payload fields.

        Override this if you need custom turn_start behavior, but call
        super().on_turn_start(ctx) to ensure mutations are applied.

        Args:
            ctx: Step context with thread state and deps

        Returns:
            None (continue execution)
        """
        # Build this plugin's event_source identifier
        my_event_source = self._get_event_source()

        # Get mutations from cached index (O(1) lookup, index built once per turn)
        mutation_index = ctx.state.get_mutation_index()
        my_mutations = mutation_index.get(my_event_source, [])

        # Apply all mutations for this plugin
        for mutation_payload in my_mutations:
            self.apply_mutation(mutation_payload)

        return None

    def _get_event_source(self) -> str:
        """Build the event_source identifier for this plugin.

        Format: {component_type}:{ClassName}:{instance_id}
        Examples:
            - "space:MultiAgentSpace:space"
            - "widget:TodoWidget:todo_001"

        Returns:
            Event source string for routing mutations
        """
        # Get component type from subclass property (explicit, not inferred)
        component_type = self.component_type

        # Build event_source
        class_name = self.__class__.__name__
        instance_id = self.instance_id or "unknown"

        return f"{component_type}:{class_name}:{instance_id}"

    @abstractmethod
    def save_mutation(self, mutation: MutationT) -> None:
        """Save mutation to ThreadProtocol.

        Stateful plugins MUST implement this to write mutations to ThreadProtocol.

        v0.0.7: data-app-chimera events now have nested structure:
        {
            "type": "data-app-chimera",
            "data": {
                "source": "{component}:{ClassName}:{instance_id}",
                "payload": {mutation serialized to dict}
            }
        }

        Args:
            mutation: The mutation to save
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement save_mutation()")

    @abstractmethod
    def apply_mutation(self, mutation: MutationT) -> None:
        """Apply mutation to plugin's local state.

        Stateful plugins MUST implement this to update their internal state.
        This is where state actually changes.

        IMPORTANT: This method should be deterministic and idempotent.
        Given the same mutation, it should always produce the same state change.

        Args:
            mutation: The mutation to apply
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement apply_mutation()")
