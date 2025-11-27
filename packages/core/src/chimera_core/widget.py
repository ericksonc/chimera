"""Widget - Base class for stateless and stateful widgets.

Widgets are BasePlugins that can be attached at two levels:
- Agent-level: Private to that agent (agent.widgets)
- Space-level: Shared across all agents (space.widgets)

Widgets implement lifecycle hooks to integrate with the conversation flow.
"""

from abc import ABC
from typing import TYPE_CHECKING, TypeVar

from .base_plugin import BasePlugin, StatefulPlugin

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
WidgetBlueprintT = TypeVar("WidgetBlueprintT")
WidgetMutationT = TypeVar("WidgetMutationT")


# ============================================================================
# WidgetMixin - Shared behavior for all widgets
# ============================================================================


class WidgetMixin:
    """Shared behavior for all widgets (stateless and stateful).

    Provides:
    - Agent reference for agent-level widgets
    - Component type identification for mutations

    This mixin uses cooperative inheritance to work with both Widget
    and StatefulWidget hierarchies without causing diamond inheritance issues.
    """

    def __init__(self):
        """Initialize widget-specific attributes.

        Uses super().__init__() to cooperate with Method Resolution Order (MRO).
        """
        super().__init__()  # Cooperates with MRO
        self._agent = None  # Set by Agent.register_widgets()

    @property
    def agent(self):
        """Read-only access to the agent that owns this widget.

        Only available for agent-level widgets. Set automatically when
        the widget is registered to an agent via Agent.register_widgets().

        Returns:
            Agent instance that owns this widget, or None if space-level widget
        """
        return self._agent


class Widget(WidgetMixin, BasePlugin[WidgetBlueprintT], ABC):
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
    is inherited from BasePlugin. Agent reference and __init__ inherited from WidgetMixin.
    """

    @property
    def component_type(self) -> str:
        """Component type for event sources.

        Returns:
            "widget" - identifies this as a widget for mutation routing
        """
        return "widget"

    # Note: __init__ and agent property inherited from WidgetMixin
    # Note: All lifecycle hooks (on_user_input, get_instructions, on_agent_output, get_toolset)
    # are inherited from BasePlugin.
    # Widgets override only the hooks they need.
    # BlueprintProtocol serialization methods (to_blueprint_config, from_blueprint_config)
    # are also inherited from BasePlugin as abstract methods.


# ============================================================================
# StatefulWidget - for widgets that maintain state via mutations
# ============================================================================


class StatefulWidget(WidgetMixin, StatefulPlugin[WidgetBlueprintT, WidgetMutationT], ABC):
    """Widget with mutable state managed through ThreadProtocol mutations.

    Stateful widgets MUST:
    1. Define both type parameters: class TodoWidget(StatefulWidget[TodoConfig, TodoMutation])
    2. Implement apply_mutation() abstract method (inherited from StatefulPlugin)
    3. Implement save_mutation() to persist to ThreadProtocol (inherited from StatefulPlugin)
    4. Use mutate() to change state (never mutate directly)

    The mutation pattern (inherited from StatefulPlugin) ensures state consistency:
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

    Note: mutate(), save_mutation(), and apply_mutation() are inherited from StatefulPlugin.
    Note: __init__ and agent property inherited from WidgetMixin.
    """

    @property
    def component_type(self) -> str:
        """Component type for event sources.

        Returns:
            "widget" - identifies this as a widget for mutation routing
        """
        return "widget"
