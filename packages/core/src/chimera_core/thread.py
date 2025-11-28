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

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Literal, Optional
from uuid import UUID

from pydantic_graph.beta import GraphBuilder, StepContext, TypeExpression

from chimera_core.base_plugin import ExecutionControl
from chimera_core.protocols.space_decision import DecidableSpace
from chimera_core.types import (
    UserInput,
    UserInputDeferredTools,
    UserInputMessage,
    UserInputScheduled,
)

logger = logging.getLogger(__name__)

# Protocols - we only import protocols, never concrete implementations
if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from .protocols import ActiveSpace
    from .threadprotocol.writer import ThreadProtocolWriter


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
    # Always required - ThreadProtocol is our single source of truth
    thread_writer: "ThreadProtocolWriter"

    # Optional dependencies (can provide mocks in tests)
    session: Optional["AsyncSession"] = None

    # Client context (propagated from UserInput) - cwd, model override, etc.
    client_context: Optional[Dict[str, Any]] = None

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
        active_space: "ActiveSpace",  # Protocol, not concrete type
        thread_builder: Optional[Any] = None,  # Legacy, unused
        parent_thread_id: Optional[UUID] = None,
        history_events: Optional[list[dict]] = None,
        user_input: Optional[UserInput] = None,
    ):
        """Initialize thread state.

        Args:
            thread_id: Unique identifier for this thread
            active_space: The space managing agents (protocol)
            thread_builder: Builds ThreadProtocol events (protocol)
            parent_thread_id: If spawned from another thread
            history_events: ThreadProtocol events from previous turns (excludes blueprint)
            user_input: Discriminated union user input (UserInputMessage | UserInputDeferredTools)
        """
        self._thread_id = thread_id
        self._active_space = active_space
        self._thread_builder = thread_builder
        self._parent_thread_id = parent_thread_id
        self._history_events = history_events or []
        self._user_input = user_input

        # Runtime flags (NOT derived state)
        self._should_stop = False

        # Mutation index cache (for O(n) widget state reconstruction)
        # Lazily built on first access, maps event_source -> list[mutation_payload]
        self._mutation_index: Optional[dict[str, list[dict]]] = None

        # Automatically reconstruct state from history (if any events provided)
        # This ensures stateful components (spaces, widgets) are in correct state
        # before thread execution begins
        if self._history_events:
            self._reconstruct_state()

    def _reconstruct_state(self) -> None:
        """Reconstruct state of stateful components from history events.

        This method automatically discovers and reconstructs state for all
        stateful components (spaces, widgets) by replaying mutations from
        ThreadProtocol history.

        Architectural principle: State reconstruction should happen transparently
        when ThreadState is created, not orchestrated by external layers.

        Discovery process:
        1. Check if active_space implements Reconstructible protocol
        2. Check all space-level widgets
        3. Check all active agent's widgets (when agents have widgets)

        This replaces manual registration in api/stream_handler.py, moving
        the orchestration logic into the core layer where it belongs.
        """
        from chimera_core.state_reconstruction import StateReconstructor

        thread_id_str = str(self._thread_id)
        reconstructor = StateReconstructor(thread_id=thread_id_str)

        # Register active_space if it's stateful
        # Check for both apply_mutation and event_source_prefix (Reconstructible protocol)
        if hasattr(self._active_space, "apply_mutation") and hasattr(
            self._active_space, "event_source_prefix"
        ):
            # Runtime check above verifies protocol compliance
            reconstructor.register(self._active_space)  # type: ignore[arg-type]
            logger.info(
                f"[thread:{thread_id_str}] Registered space for reconstruction: "
                f"type={type(self._active_space).__name__}"
            )

        # Register space-level widgets (if space has widgets attribute)
        if hasattr(self._active_space, "widgets"):
            # Defensive: check if widgets is actually iterable (list, tuple, etc.)
            try:
                widgets = self._active_space.widgets
                # Ensure it's iterable by checking for __iter__ method
                if hasattr(widgets, "__iter__"):
                    for widget in widgets:
                        if hasattr(widget, "apply_mutation") and hasattr(
                            widget, "event_source_prefix"
                        ):
                            reconstructor.register(widget)
                            logger.info(
                                f"[thread:{thread_id_str}] Registered space-level widget: "
                                f"type={type(widget).__name__}"
                            )
            except (TypeError, AttributeError):
                # Skip if widgets is not iterable (e.g., Mock object in tests)
                pass

        # Register active agent's widgets (if agent has widgets attribute)
        if hasattr(self._active_space, "active_agent"):
            active_agent = self._active_space.active_agent
            if hasattr(active_agent, "widgets"):
                # Defensive: check if widgets is actually iterable
                try:
                    widgets = active_agent.widgets
                    if hasattr(widgets, "__iter__"):
                        for widget in widgets:
                            if hasattr(widget, "apply_mutation") and hasattr(
                                widget, "event_source_prefix"
                            ):
                                reconstructor.register(widget)
                                logger.info(
                                    f"[thread:{thread_id_str}] Registered agent-level widget: "
                                    f"type={type(widget).__name__}"
                                )
                except (TypeError, AttributeError):
                    # Skip if widgets is not iterable
                    pass

        # Reconstruct state from history
        result = reconstructor.reconstruct(self._history_events, thread_id=thread_id_str)

        # Log results
        logger.info(
            f"[thread:{thread_id_str}] State reconstruction complete: "
            f"applied={result.mutations_applied} skipped={result.mutations_skipped}"
        )

        # Log errors but don't fail - partial reconstruction is better than none
        if not result.success:
            for error in result.errors:
                logger.error(f"[thread:{thread_id_str}] Reconstruction error: {error}")

    # Read-only properties
    @property
    def thread_id(self) -> UUID:
        return self._thread_id

    @property
    def active_space(self) -> "ActiveSpace":
        return self._active_space

    @property
    def should_stop(self) -> bool:
        return self._should_stop

    @property
    def user_input(self) -> Optional[UserInput]:
        """User input discriminated union (UserInputMessage | UserInputDeferredTools)."""
        return self._user_input

    # Message history access (for Agent/Transformer)
    def get_threadprotocol_events(self) -> list[dict]:
        """Get ThreadProtocol events for message history transformation.

        Returns all ThreadProtocol events from previous turns (excludes blueprint).
        This is what gets passed to the transformer to build message history.

        Returns:
            List of ThreadProtocol event dicts
        """
        return self._history_events

    def get_mutation_index(self) -> dict[str, list[dict]]:
        """Get mutation index for O(1) widget/space state reconstruction.

        Lazily builds and caches an index mapping event_source -> mutation_payloads.
        This allows StatefulPlugins to avoid O(n) event scanning on every on_turn_start().

        Performance:
        - Without index: O(n events × m plugins) = O(n×m)
        - With index: O(n events) build + O(m plugins) lookups = O(n+m)

        For 1000 events and 10 plugins: 10,000 → 1,010 operations (10x improvement)

        Returns:
            Dictionary mapping event_source to list of mutation payloads.
            Example: {"widget:TodoWidget:todo_1": [{"action": "add", ...}, ...]}
        """
        if self._mutation_index is None:
            self._mutation_index = {}

            # Build index: scan events once, group mutations by source
            for event in self._history_events:
                if event.get("type") != "data-app-chimera":
                    continue

                # v0.0.7 format: nested data.source and data.payload
                data = event.get("data", {})
                event_source = data.get("source", "")
                mutation_payload = data.get("payload", {})

                if not event_source:
                    logger.warning(f"Skipping mutation with empty event_source: {event}")
                    continue

                # Add to index
                if event_source not in self._mutation_index:
                    self._mutation_index[event_source] = []
                self._mutation_index[event_source].append(mutation_payload)

            logger.debug(
                f"Built mutation index: {len(self._mutation_index)} sources, "
                f"{sum(len(v) for v in self._mutation_index.values())} mutations"
            )

        return self._mutation_index

    # Internal mutation methods (only thread.py uses these)
    def _request_stop(self) -> None:
        """Flag that the thread should stop ASAP."""
        self._should_stop = True


# ============================================================================
# Input/Output Types
# ============================================================================


@dataclass
class ThreadInput:
    """Initial input to start/resume a thread.

    Wraps the discriminated UserInput union with user_id.
    """

    user_input: UserInput  # Discriminated union: UserInputMessage | UserInputDeferredTools
    user_id: UUID
    metadata: Optional[dict[str, Any]] = None


@dataclass
class AgentOutput:
    """Output from agent execution."""

    result: "AgentRunResult"
    # Future: spawn requests, state mutations, etc.


# ============================================================================
# Graph Definition Using Beta API
# ============================================================================

# Create the graph builder with centralized type declarations
# Note: output_type=None is valid for void graphs, but mypy doesn't understand
g = GraphBuilder(
    state_type=ThreadState,
    deps_type=ThreadDeps,
    input_type=ThreadInput,
    output_type=None,  # type: ignore[arg-type]  # Thread doesn't return anything
)


# ============================================================================
# Step Functions (Pure Business Logic)
# ============================================================================


@g.step
async def thread_start(ctx: StepContext) -> str:
    """Entry point - handles user input and initializes the thread.

    This step:
    1. Checks discriminator (UserInputMessage vs UserInputDeferredTools)
    2. For UserInputMessage: Fires hooks and emits user turn events
    3. For UserInputDeferredTools: Skips user turn events (tool events emitted in agent.py)
    4. Returns the message string (or "" for deferred tools)

    Note: Blueprint (Line 1 in JSONL) is written by the client (e.g., cli/) before
    calling run_thread(), not by thread.py.

    Returns:
        The user's message string to pass to turn_start (or "" for deferred tools)
    """
    # Extract user_input from ThreadInput
    user_input = ctx.inputs.user_input  # type: ignore[attr-defined]  # pydantic-graph TypeVar

    # Determine if this is a regular message or deferred tools
    # Use isinstance to check type (Pydantic models)
    if isinstance(user_input, UserInputMessage):
        # Regular user message - emit user turn events
        message_content = user_input.content

        # Fire on_user_input hooks (only on plugins that implement it)
        # Plugins can validate input, update state, or block the message
        callbacks = ctx.state.active_space.get_user_input_callbacks()  # type: ignore[attr-defined]
        for callback in callbacks:
            hook_result = await callback(message_content, ctx)
            if hook_result and hook_result.control != ExecutionControl.CONTINUE:
                # Plugin blocked or halted - handle accordingly
                # For now, just log it (TODO: implement proper control flow)
                print(f"Hook returned {hook_result.control}")

        # Write data-user-turn-start event (ThreadProtocol v0.0.7 - custom VSP event)
        await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
            "data-user-turn-start",
            data={"userId": str(ctx.inputs.user_id)},  # type: ignore[attr-defined]
        )

        # Emit VSP event for data-user-turn-start (boundary event - includes threadId)
        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {"type": "data-user-turn-start", "data": {"userId": str(ctx.inputs.user_id)}}  # type: ignore[attr-defined]
        )

        # Write data-user-message event (ThreadProtocol v0.0.7 - custom VSP event)
        await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
            "data-user-message", data={"content": message_content}
        )

        # Emit VSP event for data-user-message (boundary event - includes threadId)
        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {"type": "data-user-message", "data": {"content": message_content}}
        )

        # Write data-user-turn-end event (ThreadProtocol v0.0.7 - custom VSP event)
        await ctx.deps.thread_writer.write_turn_boundary("data-user-turn-end")  # type: ignore[attr-defined]

        # Emit VSP event for data-user-turn-end (boundary event - includes threadId)
        await ctx.deps.emit_vsp_event({"type": "data-user-turn-end"})  # type: ignore[attr-defined]

        # Return the message to flow through the graph
        return message_content

    elif isinstance(user_input, UserInputScheduled):
        # Scheduled/triggered execution - prompt comes from blueprint config
        # Emit user turn events like UserInputMessage, but use prompt field
        message_content = user_input.prompt

        # Fire on_user_input hooks (only on plugins that implement it)
        callbacks = ctx.state.active_space.get_user_input_callbacks()  # type: ignore[attr-defined]
        for callback in callbacks:
            hook_result = await callback(message_content, ctx)
            if hook_result and hook_result.control != ExecutionControl.CONTINUE:
                print(f"Hook returned {hook_result.control}")

        # Write data-user-turn-start event (ThreadProtocol v0.0.7)
        # Use trigger_context info if available, otherwise generic user_id
        trigger_info = user_input.trigger_context or {}
        await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
            "data-user-turn-start",
            data={"userId": trigger_info.get("schedule_id", "scheduled-trigger")},
        )

        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {
                "type": "data-user-turn-start",
                "data": {"userId": trigger_info.get("schedule_id", "scheduled-trigger")},
            }
        )

        # Write data-user-message event
        await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
            "data-user-message", data={"content": message_content}
        )

        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {"type": "data-user-message", "data": {"content": message_content}}
        )

        # Write data-user-turn-end event
        await ctx.deps.thread_writer.write_turn_boundary("data-user-turn-end")  # type: ignore[attr-defined]
        await ctx.deps.emit_vsp_event({"type": "data-user-turn-end"})  # type: ignore[attr-defined]

        return message_content

    elif isinstance(user_input, UserInputDeferredTools):
        # Deferred tools approval/denial - NO user turn events
        # Emit data-tool-approval-response events to JSONL to document user decisions
        for tool_call_id, decision in user_input.approvals.items():
            approval_event: dict[str, Any] = {
                "type": "data-tool-approval-response",
                "toolCallId": tool_call_id,
            }

            # decision can be bool or {"approved": bool, "message": str}
            if isinstance(decision, bool):
                approval_event["approved"] = decision
            elif isinstance(decision, dict):
                approval_event["approved"] = decision.get("approved", False)
                if "message" in decision:
                    approval_event["reason"] = decision["message"]

            # Emit to ThreadProtocol JSONL
            await ctx.deps.thread_writer.write_event(approval_event)  # type: ignore[attr-defined]

            # Emit VSP event (for client transparency)
            await ctx.deps.emit_vsp_event(approval_event)  # type: ignore[attr-defined]

        # Tool output events (tool-output-available/denied) will be emitted in agent.py
        # Return empty string (no user message to process)
        return ""

    else:
        # Should never happen with proper typing, but handle gracefully
        raise ValueError(f"Unknown user_input type: {type(user_input)}")


@g.step
async def turn_start(ctx: StepContext) -> str:
    """Begin a conversation turn.

    This step:
    1. Fires turn_start hooks (for ambient context and mutation application)
    2. Prepares for agent execution
    3. Passes the message through to run_agent

    Receives:
        ctx.inputs: str - The message to process (user input or previous agent response)

    Returns:
        str - The message to pass to run_agent

    Note: Turn number is calculated from ThreadProtocol, not incremented here.
    """
    # Fire turn start hooks - StatefulPlugins apply mutations here
    callbacks = ctx.state.active_space.get_turn_start_callbacks()  # type: ignore[attr-defined]
    for callback in callbacks:
        hook_result = await callback(ctx)
        if hook_result and hook_result.control != ExecutionControl.CONTINUE:
            # Plugin blocked or halted - handle accordingly
            # For now, just log it (TODO: implement proper control flow)
            print(f"on_turn_start hook returned {hook_result.control}")

    # ActiveSpace will handle agent setup when we call it
    # Pass the message through to run_agent
    return ctx.inputs


@g.step
async def run_agent(ctx: StepContext) -> AgentOutput:
    """Execute the active agent via the ActiveSpace.

    This delegates to ActiveSpace which:
    1. Determines the active agent
    2. Composes the agent's POV
    3. Runs the agent with the message and typed user_input
    4. Returns the result

    Receives:
        ctx.inputs: str - The message to process (user input or previous agent response)

    Returns:
        AgentOutput containing the result for the next step to process.
    """
    # Delegate to ActiveSpace (it knows about agents, we don't)
    # Pass the message from ctx.inputs and typed user_input from state
    result = await ctx.state.active_space.run_stream(  # type: ignore[attr-defined]
        ctx,
        ctx.inputs,
        user_input=ctx.state.user_input,  # type: ignore[attr-defined]
    )

    # Return output for next step
    return AgentOutput(result=result)


@g.step
async def turn_complete(
    ctx: StepContext[ThreadState, ThreadDeps, AgentOutput],  # type: ignore[type-arg]
) -> str | Literal["complete", "stop_requested"]:
    """Process agent output and determine next action.

    This is the decision point where we:
    1. Check safety conditions (should_stop, max consecutive agent turns)
    2. Process any state mutations from agent
    3. Record agent turn in ThreadProtocol
    4. Ask the Space whether to continue (for multi-turn orchestration)

    Returns:
        - The next prompt string (if continuing) - gets passed to turn_start
        - "complete" (if ending normally)
        - "stop_requested" (if user stopped)
    """
    agent_output = ctx.inputs  # type: ignore[attr-defined]

    # Safety checks
    if ctx.state.should_stop:  # type: ignore[attr-defined]
        print("⚠️ Thread stop requested, ending thread")
        return "stop_requested"

    # Fire on_agent_output hooks (only on plugins that implement it)
    # Plugins can react to agent output and register mutations
    callbacks = ctx.state.active_space.get_agent_output_callbacks()  # type: ignore[attr-defined]
    for callback in callbacks:
        hook_result = await callback(agent_output.result, ctx)  # type: ignore[attr-defined]
        if hook_result:
            # Handle mutations from hook result
            if hook_result.mutations:
                # TODO: Process mutations - save to ThreadProtocol, apply to state
                pass
            # Handle execution control
            if hook_result.control != ExecutionControl.CONTINUE:
                print(f"on_agent_output hook returned {hook_result.control}")
                # TODO: Handle BLOCK/HALT/AWAIT_HUMAN appropriately

    # Ask Space if it wants to continue (multi-turn orchestration)
    # Spaces implementing DecidableSpace protocol can control turn flow
    space = ctx.state.active_space  # type: ignore[attr-defined]

    if isinstance(space, DecidableSpace):
        # Space decides whether to continue
        decision = space.should_continue_turn(agent_output.result.output)  # type: ignore[attr-defined]

        if decision.decision == "continue":
            # Return the next prompt - it becomes ctx.inputs for turn_start
            return decision.next_prompt
        else:
            # Space says we're done
            return "complete"
    else:
        # Default: single turn (backward compatible)
        return "complete"


@g.step
async def thread_end(ctx: StepContext) -> None:
    """Clean up and finalize the thread."""
    print(f"Thread {ctx.state.thread_id} ended")  # type: ignore[attr-defined]


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
    # When continuing: returns the next prompt string (passed to turn_start)
    # When ending: returns "complete" or "stop_requested"
    g.edge_from(turn_complete).to(
        g.decision()
        .branch(g.match(TypeExpression[Literal["complete"]]).to(thread_end))  # type: ignore[misc]  # Normal end
        .branch(g.match(TypeExpression[Literal["stop_requested"]]).to(thread_end))  # type: ignore[misc]  # User stopped
        .branch(g.match(str).to(turn_start))  # Continue with prompt
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
    user_input: UserInput,
    user_id: UUID,
    thread_id: UUID,
    active_space: "ActiveSpace",
    deps: ThreadDeps,
    thread_builder: Optional[Any] = None,  # ThreadProtocolBuilder - optional builder
    parent_thread_id: Optional[UUID] = None,
    history_events: Optional[list[dict]] = None,
) -> ThreadState:
    """Run a thread to completion.

    This is the main entry point for thread execution. It:
    1. Creates the thread state
    2. Runs the graph with the user input
    3. Returns the final state

    Args:
        user_input: Discriminated union (UserInputMessage | UserInputDeferredTools)
        user_id: The user's ID
        thread_id: Unique ID for this thread
        active_space: The space managing agents (protocol)
        deps: External dependencies (required - includes thread_writer, emit functions)
        thread_builder: Builds ThreadProtocol events (optional)
        parent_thread_id: If spawned from another thread
        history_events: ThreadProtocol events from previous turns (excludes blueprint)

    Returns:
        The final ThreadState after execution
    """
    # Create thread state
    state = ThreadState(
        thread_id=thread_id,
        active_space=active_space,
        thread_builder=thread_builder,
        parent_thread_id=parent_thread_id,
        history_events=history_events,
        user_input=user_input,
    )

    # Create input
    input_data = ThreadInput(
        user_input=user_input,
        user_id=user_id,
    )

    # Run the graph
    try:
        await thread_graph.run(
            inputs=input_data,
            state=state,
            deps=deps,
        )
    except asyncio.CancelledError:
        # User cancelled the thread execution (halt button)
        # Log it and re-raise to propagate to caller
        logger.warning(f"[THREAD] Thread {thread_id} cancelled by user")
        raise
    except Exception as e:
        print(f"❌ Thread {thread_id} ended with error: {e}")
        raise

    return state


# ============================================================================
# Future: Thread Spawning (Parallel Execution)
# ============================================================================

# TODO: thread spawning for parallelism
#
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
