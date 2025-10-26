from typing import TYPE_CHECKING, Optional, Any, Callable
from abc import ABC
from enum import Enum

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext
    from pydantic_ai.agent import AgentRunResult
    from .thread import ThreadState, ThreadDeps, StateMutation


class ExecutionControl(Enum):
    """Control flow signals for hook results."""
    CONTINUE = "continue"
    BLOCK_ACTION = "block_action"
    HALT = "halt"
    AWAIT_HUMAN = "await_human"


class HookResult:
    """Result returned from lifecycle hooks to control execution flow."""
    
    def __init__(self, control: ExecutionControl = ExecutionControl.CONTINUE):
        self.control = control
        self.agent_message: str | None = None  # Message for agent to see
        self.user_message: str | None = None   # Message for user to see
        self.mutations: list['StateMutation'] = []
        
        # For overrides/transforms
        self.is_override = False
        self.override_value: Any = None
        self.is_transform = False
        self.transform_fn: Callable | None = None
    
    @classmethod
    def continue_with(cls, mutations=None) -> 'HookResult':
        """Continue normally, optionally with state mutations."""
        result = cls(ExecutionControl.CONTINUE)
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result
    
    @classmethod
    def override(cls, value: Any, reason: str = None, mutations=None) -> 'HookResult':
        """Override default behavior with a specific value."""
        result = cls(ExecutionControl.CONTINUE)
        result.is_override = True
        result.override_value = value
        result.agent_message = reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result
    
    @classmethod
    def transform(cls, transform_fn: Callable, reason: str = None, mutations=None) -> 'HookResult':
        """Transform the default value via a function."""
        result = cls(ExecutionControl.CONTINUE)
        result.is_transform = True
        result.transform_fn = transform_fn
        result.agent_message = reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result
    
    @classmethod
    def block(cls, reason: str, user_msg: str = None, mutations=None) -> 'HookResult':
        """Block this specific action but continue execution."""
        result = cls(ExecutionControl.BLOCK_ACTION)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result
    
    @classmethod
    def halt(cls, reason: str, user_msg: str = None, mutations=None) -> 'HookResult':
        """Halt the entire process permanently."""
        result = cls(ExecutionControl.HALT)
        result.agent_message = reason
        result.user_message = user_msg or reason
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result
    
    @classmethod
    def await_human(cls, prompt: str, mutations=None) -> 'HookResult':
        """Pause execution and wait for human approval."""
        result = cls(ExecutionControl.AWAIT_HUMAN)
        result.agent_message = "Waiting for human input..."
        result.user_message = prompt
        if mutations:
            result.mutations = mutations if isinstance(mutations, list) else [mutations]
        return result


class BasePlugin(ABC):
    """Base class for all lifecycle hook plugins.

    Plugins can hook into the process lifecycle at key points:
    - on_process_start: When a conversation begins or resumes
    - on_turn_start: At the beginning of each turn
    - on_agent_output: After an agent produces output
    - on_turn_complete: After a turn completes (mutations applied)
    - on_process_end: When the conversation ends

    All hooks receive the full graph context (ctx) which provides access to:
    - ctx.state: The current ThreadState (thread history, active space, etc.)
    - ctx.deps: ThreadDeps (database session, external services, etc.)

    Hooks can return HookResult to control execution flow, apply mutations,
    override behavior, etc. Returning None is equivalent to HookResult.continue_with().

    All methods are optional - override only the hooks you need.
    """
    
    priority: int = 0  # Override in subclasses or via decorator
    
    def __init__(self):
        self.id = self.__class__.__name__

    async def on_process_start(
        self, 
        ctx: 'GraphRunContext[ThreadState, ThreadDeps]'
    ) -> Optional[HookResult]:
        """Called when the process starts or resumes.

        Args:
            ctx: Full graph context with state and dependencies
            
        Returns:
            Optional HookResult to control execution
        """
        pass

    async def on_turn_start(
        self, 
        ctx: 'GraphRunContext[ThreadState, ThreadDeps]'
    ) -> Optional[HookResult]:
        """Called at the beginning of each agent turn.

        Args:
            ctx: Full graph context with state and dependencies
            
        Returns:
            Optional HookResult to control execution
        """
        pass

    async def on_agent_output(
        self,
        ctx: 'GraphRunContext[ThreadState, ThreadDeps]',
        result: 'AgentRunResult'
    ) -> Optional[HookResult]:
        """Called after an agent produces output.

        Args:
            ctx: Full graph context with state and dependencies
            result: The agent's output result
            
        Returns:
            Optional HookResult to control execution
        """
        pass

    async def on_turn_complete(
        self,
        ctx: 'GraphRunContext[ThreadState, ThreadDeps]',
        result: 'AgentRunResult'
    ) -> Optional[HookResult]:
        """Called after a turn completes (after mutations are applied).

        Args:
            ctx: Full graph context with state and dependencies
            result: The agent's output result
            
        Returns:
            Optional HookResult to control execution
        """
        pass

    async def on_process_end(
        self, 
        ctx: 'GraphRunContext[ThreadState, ThreadDeps]'
    ) -> Optional[HookResult]:
        """Called when the process ends.

        Args:
            ctx: Full graph context with state and dependencies
            
        Returns:
            Optional HookResult to control execution
        """
        pass