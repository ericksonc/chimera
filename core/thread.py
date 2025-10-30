"""Thread orchestration using pydantic-graph beta API.

This module implements the core execution loop of Chimera using the beta graph API
for cleaner, more explicit graph topology. It's a "dumb loop" that orchestrates
agent interactions without being coupled to specific agent/space implementations.

Key architectural principles:
1. **Thread.py knows NOTHING about concrete types** - only protocols
2. **Steps are pure functions** - business logic, not flow control
3. **Graph topology is explicit** - all flow visible in one place
4. **Data flows via ctx.inputs** - no constructor coupling
5. **Streaming path is direct** - no intermediaries

The graph follows this flow:
```
start → thread_start → turn_start → run_agent → turn_complete → decision
                                                        ↓            ↓
                                                   turn_start   thread_end → end
                                                   (continue)     (stop)
```

Migration notes from v1:
- Steps replace BaseNode classes (no boilerplate)
- GraphBuilder centralizes types (no repetition)
- Edges define flow (not return values)
- Decisions handle conditional routing
- Parallelism will be declarative (.map(), joins)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Callable, Awaitable, Literal
from uuid import UUID

from pydantic_graph.beta import GraphBuilder, StepContext, TypeExpression
from core.base_plugin import ExecutionControl

# Protocols - we only import protocols, never concrete implementations
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from .interfaces import ScenarioStore
    from .protocols import ActiveSpace, ThreadProtocolBuilder
    from .threadprotocol.writer import ThreadProtocolWriter
    from pydantic_ai.agent import AgentRunResult


# ============================================================================
# Dependencies and State
# ============================================================================

@dataclass
class ThreadDeps:
    """External dependencies injected into the graph.

    These are resources that the thread needs access to but doesn't own,
    such as database connections, API clients, configuration, and event emission.
    Thread.py doesn't know what these are - it just passes them through.
    """
    # Event emission for streaming (always required - use no-op stub if not streaming)
    emit_threadprotocol_event: Callable[[dict], Awaitable[None]]
    emit_vsp_event: Callable[[dict, bool], Awaitable[None]]

    # ThreadProtocol writer (kept open for graph lifetime, closed after)
    thread_writer: Optional['ThreadProtocolWriter'] = None

    # Optional dependencies (can provide mocks in tests)
    session: Optional['AsyncSession'] = None
    scenario_store: Optional['ScenarioStore'] = None

    # Future: API clients, external services, config overrides


class ThreadState:
    """Runtime state for thread execution.

    This is the mutable state that flows through the graph. It contains:
    - Thread identity and configuration
    - The active space (execution environment)
    - ThreadProtocol builder (event persistence)
    - Runtime flags (should_stop, etc.)

    IMPORTANT: Turn counts are DERIVED from ThreadProtocol, not tracked separately.
    This prevents state duplication and ensures ThreadProtocol is the single source of truth.
    """

    def __init__(
        self,
        thread_id: UUID,
        active_space: 'ActiveSpace',  # Protocol, not concrete type
        thread_builder: Optional['ThreadProtocolBuilder'] = None,
        parent_thread_id: Optional[UUID] = None,
        max_agent_turns_per_user_turn: int = 10,
    ):
        """Initialize thread state.

        Args:
            thread_id: Unique identifier for this thread
            active_space: The space managing agents (protocol)
            thread_builder: Builds ThreadProtocol events (protocol)
            parent_thread_id: If spawned from another thread
            max_agent_turns_per_user_turn: Safety limit - max consecutive agent turns
                without user input (prevents runaway multi-agent conversations)
        """
        self._thread_id = thread_id
        self._active_space = active_space
        self._thread_builder = thread_builder
        self._parent_thread_id = parent_thread_id
        self._max_agent_turns_per_user_turn = max_agent_turns_per_user_turn

        # Runtime flags (NOT derived state)
        self._should_stop = False
        self._child_thread_ids: list[UUID] = []

    # Read-only properties
    @property
    def thread_id(self) -> UUID:
        return self._thread_id

    @property
    def active_space(self) -> 'ActiveSpace':
        return self._active_space

    @property
    def should_stop(self) -> bool:
        return self._should_stop

    @property
    def max_agent_turns_per_user_turn(self) -> int:
        return self._max_agent_turns_per_user_turn

    # Calculated properties - derived from ThreadProtocol
    @property
    def total_turns(self) -> int:
        """Total number of turns (user + agent) in the entire thread.

        Calculated from ThreadProtocol, not tracked separately.
        """
        if not self._thread_builder:
            return 0
        # TODO: Implement via builder.get_turn_count() or similar
        # For now, stub
        return 0

    @property
    def agent_turns_since_last_user_turn(self) -> int:
        """Number of consecutive agent turns since the last user turn.

        This is what max_agent_turns_per_user_turn limits.
        In a multi-agent conversation, multiple agents might respond to one
        user message - this counts those consecutive agent turns.

        Calculated from ThreadProtocol, not tracked separately.
        """
        if not self._thread_builder:
            return 0
        # TODO: Implement via builder.get_agent_turns_since_last_user_turn()
        # Algorithm:
        # 1. Iterate events backwards from most recent
        # 2. Count agent_turn events
        # 3. Stop when we hit user_turn or start of thread
        # For now, stub
        return 0

    # Internal mutation methods (only thread.py uses these)
    def _request_stop(self) -> None:
        """Flag that the thread should stop ASAP."""
        self._should_stop = True

    def _register_child(self, child_id: UUID) -> None:
        """Track a spawned child thread."""
        self._child_thread_ids.append(child_id)


# ============================================================================
# Input/Output Types
# ============================================================================

@dataclass
class UserInput:
    """Initial input to start/resume a thread."""
    message: str
    user_id: UUID
    metadata: Optional[dict[str, Any]] = None


@dataclass
class AgentOutput:
    """Output from agent execution."""
    result: 'AgentRunResult'
    # Future: spawn requests, state mutations, etc.


# ============================================================================
# Graph Definition Using Beta API
# ============================================================================

# Create the graph builder with centralized type declarations
g = GraphBuilder(
    state_type=ThreadState,
    deps_type=ThreadDeps,
    input_type=UserInput,
    output_type=None,  # Thread doesn't return anything
)


# ============================================================================
# Step Functions (Pure Business Logic)
# ============================================================================

@g.step
async def thread_start(ctx: StepContext) -> None:
    """Entry point - handles user input and initializes the thread.

    This step:
    1. Writes blueprint (Line 1) if new thread
    2. Fires thread_start lifecycle hooks
    3. Writes user_turn_start event
    4. Transitions to first turn

    Note: No return value needed - edges define what's next.
    """
    # Write blueprint (Line 1) if this is a new thread
    if ctx.deps.thread_writer:
        # TODO: Check if file is empty/new vs resuming existing thread
        # For now, always write blueprint (assumes new thread)
        # TODO: Get actual blueprint from somewhere (ActiveSpace? ThreadState?)
        blueprint_dict = {
            "agents": [],  # TODO: Populate from ActiveSpace
            "space": {"type": "GenericSpace"},  # TODO: Actual space config
            "widgets": []  # TODO: Populate from space-level widgets
        }
        await ctx.deps.thread_writer.write_blueprint(
            thread_id=str(ctx.state.thread_id),
            blueprint=blueprint_dict
        )

    # Fire on_user_input hooks (only on plugins that implement it)
    # Plugins can validate input, update state, or block the message
    callbacks = ctx.state.active_space.get_user_input_callbacks()
    for callback in callbacks:
        hook_result = await callback(ctx.inputs.message, ctx)
        if hook_result and hook_result.control != ExecutionControl.CONTINUE:
            # Plugin blocked or halted - handle accordingly
            # For now, just log it (TODO: implement proper control flow)
            print(f"Hook returned {hook_result.control}")

    # Write user_turn_start event
    if ctx.deps.thread_writer:
        await ctx.deps.thread_writer.write_turn_boundary(
            "user_turn_start",
            user_id=str(ctx.inputs.user_id),
            timestamp=datetime.now().isoformat()
        )

    # That's it! The graph edges handle the transition.


@g.step
async def turn_start(ctx: StepContext) -> None:
    """Begin a conversation turn.

    This step:
    1. Fires turn_start hooks (for ambient context)
    2. Prepares for agent execution

    Note: Turn number is calculated from ThreadProtocol, not incremented here.
    """
    # Fire turn start hooks - widgets contribute ambient context
    # TODO: Implement lifecycle hooks
    # await ctx.state.lifecycle_hooks.fire_callbacks('on_turn_start', ctx)

    # ActiveSpace will handle agent setup when we call it


@g.step
async def run_agent(ctx: StepContext) -> AgentOutput:
    """Execute the active agent via the ActiveSpace.

    This delegates to ActiveSpace which:
    1. Determines the active agent
    2. Composes the agent's POV
    3. Runs the agent
    4. Returns the result

    Returns the agent output for the next step to process.
    """
    # Delegate to ActiveSpace (it knows about agents, we don't)
    result = await ctx.state.active_space.run_stream(ctx)

    # Fire agent output hooks
    # TODO: Implement lifecycle hooks
    # await ctx.state.hook_manager.fire("on_agent_output", ctx, result=result)

    # Return output for next step
    return AgentOutput(result=result)


@g.step
async def turn_complete(ctx: StepContext[ThreadState, ThreadDeps, AgentOutput]) -> str:
    """Process agent output and determine next action.

    This is the decision point where we:
    1. Check safety conditions (should_stop, max consecutive agent turns)
    2. Process any state mutations from agent
    3. Record agent turn in ThreadProtocol
    4. Determine whether to continue or stop

    Returns a decision indicator for routing.
    """
    agent_output = ctx.inputs

    # Safety checks
    if ctx.state.should_stop:
        print("⚠️ Thread stop requested, ending thread")
        return "stop_requested"

    # Check for runaway agent conversations (multiple agents talking without user input)
    if ctx.state.agent_turns_since_last_user_turn >= ctx.state.max_agent_turns_per_user_turn:
        print(
            f"⚠️ Hit max consecutive agent turns limit "
            f"({ctx.state.max_agent_turns_per_user_turn}), stopping"
        )
        return "max_turns_reached"

    # Fire on_agent_output hooks (only on plugins that implement it)
    # Plugins can react to agent output and register mutations
    callbacks = ctx.state.active_space.get_agent_output_callbacks()
    for callback in callbacks:
        hook_result = await callback(agent_output.result, ctx)
        if hook_result:
            # Handle mutations from hook result
            if hook_result.mutations:
                # TODO: Process mutations - save to ThreadProtocol, apply to state
                pass
            # Handle execution control
            if hook_result.control != ExecutionControl.CONTINUE:
                print(f"on_agent_output hook returned {hook_result.control}")
                # TODO: Handle BLOCK/HALT/AWAIT_HUMAN appropriately

    # Record agent turn in ThreadProtocol
    if ctx.state._thread_builder:
        ctx.state._thread_builder.add_agent_turn(
            agent_id=ctx.state.active_space.active_agent.id,
            result=agent_output.result,
            timestamp=datetime.now(),
        )

    # Determine next action
    # TODO: Check if space wants to continue (multi-agent orchestration)
    # should_continue = await ctx.state.active_space.should_continue()
    should_continue = False  # For now, single turn only

    return "continue" if should_continue else "complete"


@g.step
async def thread_end(ctx: StepContext) -> None:
    """Clean up and finalize the thread.

    This step:
    1. Fires thread_end hooks
    2. Finalizes ThreadProtocol
    """
    # Fire thread end hooks (for cleanup, logging, etc.)
    # TODO: Implement lifecycle hooks
    # await ctx.state.hook_manager.fire("on_thread_end", ctx)

    # Finalize ThreadProtocol
    if ctx.state._thread_builder:
        await ctx.state._thread_builder.finalize()

    print(f"Thread {ctx.state.thread_id} ended")


# ============================================================================
# Graph Topology (Explicit Flow Definition)
# ============================================================================

# Define the complete graph topology in ONE place
g.add(
    # Main flow: start → thread_start → turn_start → run_agent → turn_complete
    g.edge_from(g.start_node).to(thread_start),
    g.edge_from(thread_start).to(turn_start),
    g.edge_from(turn_start).to(run_agent),
    g.edge_from(run_agent).to(turn_complete),

    # Conditional routing from turn_complete via decision node
    g.edge_from(turn_complete).to(
        g.decision()
        .branch(g.match(TypeExpression[Literal["continue"]]).to(turn_start))         # Loop back
        .branch(g.match(TypeExpression[Literal["complete"]]).to(thread_end))         # Normal end
        .branch(g.match(TypeExpression[Literal["stop_requested"]]).to(thread_end))   # User stopped
        .branch(g.match(TypeExpression[Literal["max_turns_reached"]]).to(thread_end)) # Safety limit
    ),

    # Terminal
    g.edge_from(thread_end).to(g.end_node),
)

# Build the graph
thread_graph = g.build()


# ============================================================================
# Public API
# ============================================================================

async def run_thread(
    user_input: str,
    user_id: UUID,
    thread_id: UUID,
    active_space: 'ActiveSpace',
    thread_builder: Optional['ThreadProtocolBuilder'] = None,
    deps: Optional[ThreadDeps] = None,
    parent_thread_id: Optional[UUID] = None,
) -> ThreadState:
    """Run a thread to completion.

    This is the main entry point for thread execution. It:
    1. Creates the thread state
    2. Runs the graph with the user input
    3. Returns the final state

    Args:
        user_input: The user's message
        user_id: The user's ID
        thread_id: Unique ID for this thread
        active_space: The space managing agents (protocol)
        thread_builder: Builds ThreadProtocol events (optional)
        deps: External dependencies (optional)
        parent_thread_id: If spawned from another thread

    Returns:
        The final ThreadState after execution
    """
    # Create thread state
    state = ThreadState(
        thread_id=thread_id,
        active_space=active_space,
        thread_builder=thread_builder,
        parent_thread_id=parent_thread_id,
    )

    # Create input
    input_data = UserInput(
        message=user_input,
        user_id=user_id,
    )

    # Run the graph
    try:
        await thread_graph.run(
            input_data,
            state=state,
            deps=deps or ThreadDeps(),
        )
    except Exception as e:
        print(f"❌ Thread {thread_id} ended with error: {e}")
        raise

    return state


# ============================================================================
# Future: Thread Spawning (Parallel Execution)
# ============================================================================

# When we need parallel DM spawning, we'll add:
#
# @g.step
# async def detect_spawn_requests(ctx: StepContext[ThreadState, ThreadDeps, AgentOutput]) -> list[SpawnRequest]:
#     """Extract any thread spawn requests from agent output."""
#     # Extract spawn requests (DMs, parallel tasks, etc.)
#     pass
#
# @g.step
# async def spawn_child_thread(ctx: StepContext[ThreadState, ThreadDeps, SpawnRequest]) -> ChildResult:
#     """Spawn and run a child thread with isolated state."""
#     # Create new ThreadState, run thread_graph, return result
#     pass
#
# # Parallel spawning with join
# collect_children = g.join(reduce_list_append, initial_factory=list)
# g.add(
#     g.edge_from(detect_spawns).map().to(spawn_child_thread),  # Parallel
#     g.edge_from(spawn_child_thread).to(collect_children),      # Join
# )