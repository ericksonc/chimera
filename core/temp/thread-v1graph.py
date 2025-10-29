"""Process orchestration graph - the core execution loop of Prometheus MAS.

This module implements a "dumb loop" using pydantic-graph that orchestrates
agent interactions without being tightly coupled to specific agent or cell 
implementations. It serves as the execution engine that:

1. **Manages Process Flow**: Controls the sequence of turns in conversations
2. **Fires Lifecycle Hooks**: Triggers hooks at key points (process/turn start/end)
3. **Handles State Mutations**: Applies changes from agent outputs (agent switching, DM spawning)
4. **Supports Process Spawning**: Can spawn child processes for isolated conversations (DMs)

The process graph follows this flow:
```
ProcessStart -> TurnStart -> RunAgent -> TurnComplete -> [TurnStart or ProcessEnd]
```

Key abstractions:
- **ThreadState**: Carries all runtime state through the graph
- **ActiveSpace Protocol**: Abstraction for different conversation types (GroupChat, DM)
- **StateMutation**: Declarative changes to be applied to state
- **Lifecycle Hooks**: Extension points for adding behavior without modifying core

TODO: run each process/thread in asyncio.create_task
If the user hits the cancel button, we simply cancel the task, and Pydantic AI stops inference on the LLM right away.



"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Any, TYPE_CHECKING, Optional
from uuid import UUID

from pydantic_graph import (
    BaseNode,
    End,
    Graph,
    GraphRunContext,
)
from pydantic_ai.agent import AgentRunResult

from datetime import datetime

# More imports

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from .interfaces import ScenarioStore

@dataclass
class ThreadDeps:
    """Dependencies available to all nodes and plugins via ctx.deps.
    
    These are external resources that the process needs access to,
    such as database connections, API clients, etc. They are passed
    through the graph context and made available to all lifecycle hooks.
    """
    session: Optional['AsyncSession'] = None
    # Future: API clients, external services, config overrides, etc.

    @property
    def history(self) -> ThreadProtocol:
      # canonical list of everything that's happened so far
      pass
    
    @property
    def scenario_config(self) -> ScenarioStore:
      # load up turn 0 configuration
      pass


class ThreadState:
    """State for the process orchestration loop.
    
    This represents the runtime state that flows through the process graph.
    It contains both the configuration needed to run the process and the
    accumulated state (messages) as the process executes.
    
    All fields are read-only properties to enforce that only process.py 
    should mutate state directly. Other components should register state 
    mutations to be applied by the process orchestration.
    
    This class implements both ReadableThreadState (for read-only access)
    and MutableThreadState (for orchestration) protocols.
    """
    
    def __init__(
        self,
        id: UUID,
        
        thread_config: ThreadConfig,
        active_space: ActiveSpace,  # Instead, just resolve this from ThreadConfig and remove this from __init__
        # turn_number: int = 0, # Just keep track of list of Agent / User Turns in ThreadProtocol, have this be computed field
        

        # not sure which of these we'll need...

        # config: ProcessConfig = None,
        # hook_manager: HookManager = None,
        # instruction_aggregator: InstructionAggregator = None,
        # output_registry: Any = None,
        # messages: list[ChimeraMessage] = None,
        # external_messages: list[ChimeraMessage] = None,
        # process_stack: list['ThreadState'] = None,
        # parent_turn_number: int | None = None,
        # message_artifacts: dict[UUID, Any] = None,
        # scenario: Optional['Scenario'] = None,
        # status: ProcessStatus = ProcessStatus.ACTIVE,
        # should_stop: bool = False,
    ):
        """Initialize ThreadState with all fields as private attributes."""
        self._id = id
        self._active_space = active_space
        self._should_stop = False  # Memory-only flag for stopping the process. if True, stop ASAP.a

        # ThreadProtocol builder for capturing conversation history
        self._thread_builder = thread_builder or ThreadProtocolBuilder(thread_id=id)

        # Transient field for ThreadDeps (not persisted, set during execution)
        self._deps: Optional[ThreadDeps] = None
    
    # Read-only properties for all fields?



class ActiveSpace(Protocol):
    """Protocol for orchestrating process flow.
    
    This abstraction allows process.py to control flow without
    being coupled to specific cell implementations.
    """
    
    @property
    def active_agent(self) -> Agent:
        """The currently active agent."""
        ...
    
    async def run(self, state: ThreadState) -> Any:
        """Run the active agent and return its output."""
        ...
    
    async def run_stream(self, state: ThreadState) -> Any:
        """Run the active agent and return its output while streaming vercel api sdk formatted token deltas"""
        ...
    


@dataclass
class ProcessStart(BaseNode[ThreadState, ThreadDeps]):
    """Entry node for the process graph.
    
    This is where every conversation begins OR resumes. It handles the user's input,
    initializes/resumes the process, fires process_start hooks, and transitions 
    to the first turn.
    
    Args:
        user_input: The user's message (whether starting fresh or resuming)
        user_id: Optional user ID (None for now until user system is implemented)
    
    Hooks fired: on_process_start, on_message_created (for user message)
    Next node: TurnStart
    """

    # TODO: could be a wide range of input structures we might allow. Not to mention in the case of e.g. multimodal...
    # ...should look closely at ThreadProtocol to decide this. 
    user_input: Any 

    user_id: UUID  # Just hardcode a UUID of all zeroes for now
    
    async def run(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> TurnStart:

        # Fire process start hooks - pass full context

        # Vue-like lifecycle hooks; various code can register callbacks
        await ctx.state.lifecycle_hooks.fire_callbacks('on_process_start', ctx)  
        # instructions (for types, see "instructions" in pydantic AI docs) get auto-registered
        
        # Create and add the user message in ThreadProtocol

        ctx.state.thread_builder.start_user_turn(
            user_input=self.user_input,
            timestamp=datetime.now()
        )

        return TurnStart()


@dataclass
class TurnStart(BaseNode[ThreadState, ThreadDeps]):
    """Node that begins each conversation turn.
    
    This node increments the turn counter, clears the instruction aggregator
    for fresh instructions, and fires turn_start hooks. Hooks can contribute
    instructions that will be passed to the agent.
    
    Hooks fired: on_turn_start (with agent_id if available)
    Next node: RunAgent
    """
    async def run(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> RunAgent:
        
        # Fire turn start hooks - pass full context
        ctx.state.lifecycle_hooks.fire_callbacks('on_turn_start', ctx)  
        # instructions (for types, see "instructions" in pydantic AI docs) get auto-registered

        # The ActiveSpace is responsible for setting up the agent
        
        return RunAgent()


@dataclass  
class RunAgent(BaseNode[ThreadState, ThreadDeps]):
    """Node that executes the active agent.
    
    This delegates to the ActiveSpace to run its current agent. The cell handles
    passing instructions, message history, and output schema to the agent.
    The agent's output is then passed to TurnComplete for processing.
    
    Hooks fired: on_agent_output
    Next node: TurnComplete
    """
    async def run(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> TurnComplete:
      
        # TODO: actually run ctx.state.active_space.run_stream(ctx.state)
        result:AgentRunResult[OutputDataT] = ctx.state.active_space.run_stream(ctx.state)

        # TODO: process agent output (result: AgentRunResult[OutputDataT])
        await ctx.state.hook_manager.fire("on_agent_output", ctx, result=result)
        
        return TurnComplete(result:AgentRunResult[OutputDataT])


@dataclass
class TurnComplete(BaseNode[ThreadState, ThreadDeps]):
    """Node that processes agent output and determines next action.
    
    This is the decision point where agent output is interpreted:
    1. Find the appropriate handler using OutputRegistry
    2. Get a StateMutation from the handler
    3. Apply the mutation (could spawn DM, switch agents, or end process)
    4. Store the agent's message in history
    5. Transition to next turn or end
    
    This node also handles DM spawning - if a mutation includes spawn_child,
    it runs the child process synchronously and handles message artifacts.
    
    Hooks fired: on_turn_complete
    Next node: TurnStart (continue) or ProcessEnd (terminate)
    """
    result: AgentRunResult[OutputDataT]
    
    async def run(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> ProcessEnd | TurnStart:
        
        # maybe put these in a separate helper function to keep the main graph cleaner...
        # Check if process should stop (e.g., from API stop request)
        if ctx.state.should_stop:
            print(f"⚠️  Process stop requested, ending process")
            return ProcessEnd()

        # Safety check: prevent runaway conversations
        if ctx.state.turn_number >= ctx.state.config.max_turns:
            print(f"⚠️  Hit max turns limit ({ctx.state.config.max_turns}), forcing end")
            return ProcessEnd()


        # Gather state mutations

        # Apply state mutations

        # add AgentTurn to ThreadProtocol

        await ctx.state.hook_manager.fire("on_turn_complete", ctx, result=result)
        
        # Apply the mutation
        
            # Spawning a child process e.g. agent leaves cell, parallelism, etc.
        
        if should_continue:
            # If we know that another agent should synchronously take another turn in this thread/process, start their turn
            return TurnStart()
        else:
            return ProcessEnd()


@dataclass
class ProcessEnd(BaseNode[ThreadState, ThreadDeps]):
    """Terminal node for the process graph.
    
    This node fires process_end hooks, logs statistics about the conversation,
    and returns the final turn count. This is where cleanup and finalization
    happen before the process terminates.
    
    Hooks fired: on_process_end
    Returns: Number of turns completed
    """
    async def run(self, ctx: GraphRunContext[ThreadState, ThreadDeps]) -> End:
        ctx.state._set_status(ProcessStatus.COMPLETED)
        
        # Emit the "done" events to all clients- the AI is finished for now.
        
        # Fire process end hook - pass full context
        # This hook is especially used for any end-of-process logging etc.
        await ctx.state.hook_manager.fire("on_process_end", ctx)
        
        return End()


async def run_process(state: ThreadState) -> ThreadState:
    """Run a complete process to completion.
    
    This is used for spawning child processes synchronously.
    The parent process blocks until this completes.
    If any exception occurs during execution, the process status
    is set to ERROR before re-raising the exception.
    """
    try:
        result = await process_graph.run(ProcessStart(), state=state)
    except Exception as e:
        # Set ERROR status on any unhandled exception
        state._set_status(ProcessStatus.ERROR)
        print(f"❌ Process ended with error: {e}")
        raise  # Re-raise the exception for caller to handle
    
    return state  # Return the updated state with all messages/artifacts


process_graph = Graph(
    nodes=(ProcessStart, TurnStart, RunAgent, TurnComplete, ProcessEnd), 
    state_type=ThreadState,
)
