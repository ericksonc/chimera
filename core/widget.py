"""Widget Lifecycle Adapter

This adapter allows widgets to implement a simple interface while still
participating in the lifecycle hook system.
"""

from typing import TYPE_CHECKING, Optional, Any, Dict, Callable, List, TypeVar, Generic
from uuid import UUID
from abc import ABC, abstractmethod
from .baseplugin import BasePlugin, HookResult

from pydantic_graph import GraphRunContext
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.tools import Tool, Toolset
from .thread import ThreadState, ThreadDeps

if TYPE_CHECKING:
    from .threadprotocol.blueprint import WidgetConfig

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


class Widget(BasePlugin, ABC):
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
    """

    # Widget metadata - must be set by subclasses
    widget_class_name: str = None  # e.g., "chimera.widgets.CodeWindowWidget"
    widget_version: str = None      # e.g., "1.0.0"

    def __init__(self):
        """Initialize base widget."""
        super().__init__()  # Initialize base class
        self.instance_id: str = None  # Set during registration

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
    
    def available_tools(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> Optional[List[Tool]]:
        """
        Provide any tools the agent should receive.
        Can inspect agent / thread state via ctx to conditionally apply tools.
        e.g. only provide tools to a particular agent name / type / configuration etc.
        """
        pass

    # BlueprintProtocol serialization - components own their own serialization

    def to_blueprint_config(self) -> "WidgetConfig[WidgetBlueprintT]":
        """Serialize this widget instance to BlueprintProtocol format.

        Subclasses MUST override this to provide their typed config.

        Returns:
            WidgetConfig[WidgetBlueprintT]: Typed widget configuration
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement to_blueprint_config()"
        )

    @classmethod
    def from_blueprint_config(cls, config: "WidgetConfig[WidgetBlueprintT]") -> "Widget":
        """Deserialize widget instance from BlueprintProtocol format.

        Subclasses MUST override this to implement deserialization.

        Args:
            config: Typed WidgetConfig with widget-specific config

        Returns:
            Widget instance
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement from_blueprint_config()"
        )

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

class StatefulWidget(Widget, Generic[WidgetMutationT], ABC):
    """Widget with mutable state managed through ThreadProtocol mutations.

    Stateful widgets MUST:
    1. Define WidgetMutationT type
    2. Implement apply_mutation() abstract method
    3. Use mutate() to change state (never mutate directly)

    The mutation pattern ensures state consistency:
    - Runtime state matches what's in ThreadProtocol
    - Thread replay produces identical state
    - State changes are auditable
    """

    def mutate(self, mutation: WidgetMutationT):
        """Mutate widget state via ThreadProtocol.

        This is the ONLY way to change widget state:
        1. Save mutation to ThreadProtocol (persistence)
        2. Apply mutation to local state (runtime)

        Args:
            mutation: Typed mutation describing state change
        """
        self.save_mutation(mutation)  # TODO: Implement ThreadProtocol writer
        self.apply_mutation(mutation)

    def save_mutation(self, mutation: WidgetMutationT):
        """Save mutation to ThreadProtocol.

        TODO: Implement using centralized ThreadProtocol writer.
        This should write a data-app-chimera event with:
        - event_source: "widget:{ClassName}:{instance_id}"
        - data: mutation serialized to dict
        """
        raise NotImplementedError("save_mutation not yet implemented")

    @abstractmethod
    def apply_mutation(self, mutation: WidgetMutationT):
        """Apply mutation to widget's local state.

        This is where state actually changes. MUST be implemented by subclasses.

        Args:
            mutation: The mutation to apply
        """
        pass