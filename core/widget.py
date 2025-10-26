"""Widget Lifecycle Adapter

This adapter allows widgets to implement a simple interface while still
participating in the lifecycle hook system.
"""

from typing import TYPE_CHECKING, Optional, Any, Dict, Callable, List, TypeVar, Generic
from uuid import UUID
from abc import ABC
from .baseplugin import BasePlugin, HookResult

from pydantic_graph import GraphRunContext
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.tools import Tool, Toolset
from .thread import ThreadState, ThreadDeps

"""
Widgets can be stateful. But state must only be edited through state mutations.
WidgetMutationT represents the type of state mutation this widget can read/write to ThreadProtocol.
# TODO: refactor state-based behavior to subclass StatefulWidget

If the widget would change its own state- e.g. as a result of agent using a tool, or because of agent output-
it must first create a mutation of type WidgetMutationT, and use the persistence store to save it.

*Then* it modifies its own state by *running* the mutation it just created.

This ensures that "state at runtime" and "state during playback" are always aligned.
"""
WidgetMutationT = TypeVar('WidgetMutationT') 


class Widget(BasePlugin, ABC):
    """Adapter that delegates lifecycle events to widget methods.
    
    This allows widgets to have a simpler interface while still
    working with the hook system. The adapter handles:
    - Converting widget methods to hook events
    - Managing HookResult wrapping
    - Integrating with the instruction aggregator
    """
    
    def __init__(self, widget: Widget):
        """Initialize adapter with the widget to delegate to.
        
        Args:
            widget: The widget instance to adapt
        """
        super().__init__()  # Initialize base class
        self.widget = widget

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
        Can inspect agent / thread state via ctx to consitionally apply tools. 
        e.g. only provide tools to a particular agent name / type / configuration etc.
        """
        pass
    
    def mutate(self, mutation: WidgetMutationT):
        """
        To mutate state, a valid WidgetMutationT must be created- this will be both persisted and executed.
        """
        self.save_mutation(mutation) # Not implemented yet.. Should use some centralized thing to write ThreadProtocol.
        self.apply_mutation(mutation)
    
    def apply_mutation(mutation:WidgetMutationT):
        """ 
        MUST be implemented by all stateful widgets (TODO: Refactor into subclass StatefulWidget as abstract method)
        This is where we *actually mutate state* based on the mutation.
        """
        pass

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