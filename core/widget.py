"""Widget Lifecycle Adapter

This adapter allows widgets to implement a simple interface while still
participating in the lifecycle hook system.
"""

from typing import TYPE_CHECKING, Optional, Any, TypeVar
from abc import ABC
from .base_plugin import BasePlugin, HookResult

from pydantic_graph import GraphRunContext
from pydantic_ai import FunctionToolset
from .thread import ThreadState, ThreadDeps

if TYPE_CHECKING:
    pass

"""
Widgets can be stateful. But state must only be edited through state mutations.
WidgetMutationT represents the type of state mutation this widget can read/write to ThreadProtocol.
# TODO: refactor state-based behavior to subclass StatefulWidget

If the widget would change its own state- e.g. as a result of agent using a tool, or because of agent output-
it must first create a mutation of type WidgetMutationT, and use the persistence store to save it.

*Then* it modifies its own state by *running* the mutation it just created.

This ensures that "state at runtime" and "state during playback" are always aligned.
"""
WidgetBlueprintT = TypeVar('WidgetBlueprintT')
WidgetMutationT = TypeVar('WidgetMutationT')


class Widget(BasePlugin[WidgetBlueprintT, Any], ABC):
    """Base widget class for stateless widgets.

    This allows widgets to have a simpler interface while still
    working with the hook system. The adapter handles:
    - Converting widget methods to hook events
    - Managing HookResult wrapping
    - Integrating with the instruction aggregator

    All widgets define:
    - WidgetBlueprintT: Turn 0 configuration type (in BlueprintProtocol)

    For stateful widgets, use StatefulWidget subclass which adds:
    - WidgetMutationT: Runtime state mutation type (in ThreadProtocol events)

    Note: Widget metadata (component_class_name, component_version, instance_id)
    is inherited from BasePlugin.
    """

    def __init__(self):
        """Initialize base widget."""
        super().__init__()  # Initialize base class

    # Main Interface

    def ambient_context(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> str | None:
        """ 
        Return string which should appear as ambient context for the agent. 
        Think of ambient context as the "persistent UI you're giving the agent for this Widget."
        Only used when there's something about this widget that should be "always shown" in system instructions 
        (i.e. not within thread history) as opposed to just being a return value for tools.
        """
        pass
    
    def process_output(self, ctx: GraphRunContext[ThreadState, ThreadDeps], output):
        """
        If the Widget needs to do something (e.g. modify its state) as a result of the agent's final output, implement this method.
        """
        pass
    
    def available_tools(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> Optional[FunctionToolset]:
        """
        Provide a toolset that the agent should receive.

        Returns a FunctionToolset containing the widget's tools.
        Can inspect agent / thread state via ctx to conditionally provide tools.

        Example:
            toolset = FunctionToolset()

            @toolset.tool
            def widget_action(param: str) -> str:
                return f"Action: {param}"

            return toolset
        """
        pass

    # Note: BlueprintProtocol serialization methods (to_blueprint_config, from_blueprint_config)
    # are inherited from BasePlugin as abstract methods

    # Implementation (maybe refactor this, maybe have some thing via composition use lifecycle hooks rather than provide them directly)
    
    async def on_turn_start(self, ctx) -> HookResult:
        """Provide widget's ambient context to the agent.
        
        Delegates to widget.get_ambient_context() if the method exists.
        
        Args:
            ctx: GraphRunContext containing state and deps
            
        Returns:
            HookResult with ambient context in environment category
        """
        await super().on_turn_start(ctx)

        ambient_context = self.ambient_context(ctx)
        if ambient_context:
          # TODO: inject this widget's ambient context
          pass


        return
    # similarly, use simple hook to provide output to process_output


# ============================================================================
# StatefulWidget - for widgets that maintain state via mutations
# ============================================================================

class StatefulWidget(BasePlugin[WidgetBlueprintT, WidgetMutationT], ABC):
    """Widget with mutable state managed through ThreadProtocol mutations.

    Stateful widgets MUST:
    1. Define both type parameters: class TodoWidget(StatefulWidget[TodoConfig, TodoMutation])
    2. Implement apply_mutation() abstract method (inherited from BasePlugin)
    3. Implement save_mutation() to persist to ThreadProtocol (inherited from BasePlugin)
    4. Use mutate() to change state (never mutate directly)

    The mutation pattern (inherited from BasePlugin) ensures state consistency:
    - Runtime state matches what's in ThreadProtocol
    - Thread replay produces identical state
    - State changes are auditable

    Example:
        @dataclass
        class TodoConfig:
            initial_todos: list[str]

        @dataclass
        class TodoMutation:
            action: Literal["add", "remove"]
            todo_id: str
            text: str | None = None

        class TodoWidget(StatefulWidget[TodoConfig, TodoMutation]):
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

    Note: mutate(), save_mutation(), and apply_mutation() are inherited from BasePlugin.
    """
    pass