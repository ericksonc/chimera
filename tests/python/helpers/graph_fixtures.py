"""Graph builder fixtures and helpers for testing.

Provides reusable graph configurations for common testing scenarios.
Use these to test execution flow without rebuilding graphs from scratch.
"""

from pydantic_ai.run import AgentRunResult
from pydantic_graph.beta import GraphBuilder, StepContext

from chimera_core.thread import (
    AgentOutput,
    ThreadDeps,
    ThreadState,
    UserInput,
    run_agent,
    thread_start,
    turn_start,
)


def create_graph_builder() -> GraphBuilder:
    """Create a GraphBuilder with correct types for thread testing.

    Returns:
        GraphBuilder configured for ThreadState, ThreadDeps, UserInput
    """
    return GraphBuilder(
        state_type=ThreadState,
        deps_type=ThreadDeps,
        input_type=UserInput,
        output_type=None,
    )


def build_minimal_graph() -> object:
    """Build minimal test graph: start -> thread_start -> turn_start -> end.

    Use this to test lifecycle hooks without agent execution.

    Example:
        graph = build_minimal_graph()
        await graph.run(inputs=user_input, state=thread_state, deps=deps)
        # Verify hooks fired, events emitted
    """
    g = create_graph_builder()
    g.add(
        g.edge_from(g.start_node).to(thread_start),
        g.edge_from(thread_start).to(turn_start),
        g.edge_from(turn_start).to(g.end_node),
    )
    return g.build()


def build_single_turn_graph(mock_run_agent_step=None) -> object:
    """Build graph for single agent turn: start -> ... -> run_agent -> end.

    Use this to test full turn execution with a mock agent.

    Args:
        mock_run_agent_step: Optional custom run_agent step (for testing)
            If None, you'll need to provide a real space with agent

    Example:
        # With mock agent
        @g.step
        async def mock_run_agent(ctx: StepContext) -> AgentOutput:
            return AgentOutput(result=mock_result)

        graph = build_single_turn_graph(mock_run_agent)
        await graph.run(inputs=user_input, state=thread_state, deps=deps)
    """
    g = create_graph_builder()

    # Use provided mock or real run_agent step
    agent_step = mock_run_agent_step if mock_run_agent_step else run_agent

    g.add(
        g.edge_from(g.start_node).to(thread_start),
        g.edge_from(thread_start).to(turn_start),
        g.edge_from(turn_start).to(agent_step),
        g.edge_from(agent_step).to(g.end_node),
    )
    return g.build()


def build_full_flow_graph() -> object:
    """Build the full thread execution graph with decision routing.

    This is the complete graph from thread.py:
    start -> thread_start -> turn_start -> run_agent -> turn_complete -> decision
                                                    ↓            ↓
                                               turn_start   thread_end -> end
                                               (continue)     (stop)

    Use this to test:
    - Multi-turn agent conversations
    - Decision routing logic
    - Safety limits (max_agent_turns_per_user_turn)

    Example:
        graph = build_full_flow_graph()
        await graph.run(inputs=user_input, state=thread_state, deps=deps)
        # Verify correct decision path taken
    """
    from chimera_core.thread import thread_graph

    # Just return the actual graph from thread.py
    # It's already built with all decision routing
    return thread_graph


def create_mock_agent_output(
    result_text: str = "Mock agent response", deferred_tools: bool = False
) -> AgentOutput:
    """Create a mock AgentOutput for testing.

    Args:
        result_text: Text for the agent's response
        deferred_tools: If True, set output to DeferredToolRequests

    Returns:
        AgentOutput suitable for testing

    Example:
        @g.step
        async def mock_run_agent(ctx: StepContext) -> AgentOutput:
            return create_mock_agent_output("Hello!")
    """
    # This is a simplified mock - in real tests you'd create a full AgentRunResult
    # For now, just create a minimal structure
    from unittest.mock import Mock

    mock_result = Mock(spec=AgentRunResult)
    mock_result.data = result_text

    if deferred_tools:
        from pydantic_ai.output import DeferredToolRequests

        mock_result.output = DeferredToolRequests(approvals=[], calls=[])
    else:
        mock_result.output = result_text

    return AgentOutput(result=mock_result)


def create_mock_run_agent_step(g: GraphBuilder, result_text: str = "Mock response"):
    """Create a mock run_agent step that returns predetermined result.

    Args:
        g: GraphBuilder instance
        result_text: Text to return from agent

    Returns:
        Graph step function

    Example:
        g = create_graph_builder()
        mock_agent = create_mock_run_agent_step(g, "Hello!")

        g.add(
            g.edge_from(g.start_node).to(thread_start),
            g.edge_from(thread_start).to(turn_start),
            g.edge_from(turn_start).to(mock_agent),
            g.edge_from(mock_agent).to(g.end_node),
        )
        graph = g.build()
    """

    @g.step
    async def mock_run_agent(ctx: StepContext) -> AgentOutput:
        """Mock agent that returns predetermined response."""
        return create_mock_agent_output(result_text)

    return mock_run_agent
