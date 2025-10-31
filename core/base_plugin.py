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
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Optional, TypeVar, Generic

if TYPE_CHECKING:
    from pydantic_graph.beta import StepContext
    from .protocols import ReadableThreadState
    from pydantic_ai.agent import AgentRunResult
    from pydantic_ai.toolsets import FunctionToolset
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

BlueprintT = TypeVar('BlueprintT')  # Turn 0 configuration type
MutationT = TypeVar('MutationT')    # Runtime state mutation type


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
        self.user_message: str | None = None   # Message for user to see
        self.mutations: list[MutationT] = []

    @classmethod
    def continue_with(cls, mutations: list[MutationT] | MutationT | None = None) -> 'HookResult[MutationT]':
        """Continue normally, optionally with state mutations."""
        result = cls(ExecutionControl.CONTINUE)
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def block(cls, reason: str, user_msg: str | None = None, mutations: list[MutationT] | MutationT | None = None) -> 'HookResult[MutationT]':
        """Block this specific action but continue execution."""
        result = cls(ExecutionControl.BLOCK_ACTION)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def halt(cls, reason: str, user_msg: str | None = None, mutations: list[MutationT] | MutationT | None = None) -> 'HookResult[MutationT]':
        """Halt the entire process permanently."""
        result = cls(ExecutionControl.HALT)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result

    @classmethod
    def await_human(cls, prompt: str, mutations: list[MutationT] | MutationT | None = None) -> 'HookResult[MutationT]':
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

class BasePlugin(Generic[BlueprintT], ABC):
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

    Example:
        class ContextDocsWidget(BasePlugin[ContextDocsConfig]):
            # Stateless widget - no mutations
            ...
    """

    # Component metadata - must be set by subclasses
    component_class_name: str = None  # e.g., "chimera.widgets.CodeWindowWidget"
    component_version: str = None      # e.g., "1.0.0"
    instance_id: str = None            # Set during registration

    async def on_user_input(self, message: str, ctx: 'StepContext') -> Optional['HookResult[Any]']:
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

    async def on_agent_output(self, result: 'AgentRunResult', ctx: 'StepContext') -> Optional['HookResult[Any]']:
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

    # ========================================================================
    # BlueprintProtocol Serialization
    # ========================================================================

    @abstractmethod
    def to_blueprint_config(self) -> "ComponentConfig[BlueprintT]":
        """Serialize this component instance to BlueprintProtocol format.

        Components own their own serialization. This method converts the runtime
        component instance into its configuration representation for storage.

        Returns:
            ComponentConfig[BlueprintT]: Typed component configuration

        Example:
            def to_blueprint_config(self) -> ComponentConfig[TodoConfig]:
                return ComponentConfig(
                    class_name=self.component_class_name,
                    version=self.component_version,
                    instance_id=self.instance_id,
                    config=TodoConfig(
                        initial_todos=self.todos
                    )
                )
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement to_blueprint_config()"
        )

    @classmethod
    @abstractmethod
    def from_blueprint_config(cls, config: "ComponentConfig[BlueprintT]") -> "BasePlugin[BlueprintT, MutationT]":
        """Deserialize component instance from BlueprintProtocol format.

        Creates a new component instance from stored configuration.

        Args:
            config: Typed ComponentConfig with component-specific config

        Returns:
            Component instance

        Example:
            @classmethod
            def from_blueprint_config(cls, config: ComponentConfig[TodoConfig]) -> TodoWidget:
                widget = cls()
                widget.instance_id = config.instance_id
                widget.todos = config.config.initial_todos
                return widget
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement from_blueprint_config()"
        )


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

            def apply_mutation(self, mutation: TodoMutation) -> None:
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

    @abstractmethod
    def save_mutation(self, mutation: MutationT) -> None:
        """Save mutation to ThreadProtocol.

        Stateful plugins MUST implement this to write mutations to ThreadProtocol.
        This should write a data-app-chimera event with:
        - event_source: "{component}:{ClassName}:{instance_id}"
        - data: mutation serialized to dict

        Args:
            mutation: The mutation to save
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement save_mutation()"
        )

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
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement apply_mutation()"
        )
