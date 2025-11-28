"""FunctionModel helpers for deterministic multi-turn testing.

FunctionModel allows precise control over agent responses in tests,
enabling deterministic testing of complex conversation flows, tool calls,
and multi-agent orchestration without actual LLM API calls.

Example:
    # Test agent switching
    model = create_agent_switching_model("unreal-engine-expert")
    with agent.override(model=model):
        # Agent will call switch_active_agent tool deterministically
        await space.run(...)

    # Test multi-turn conversation
    model = create_multi_turn_model(["First response", "Second response"])
    with agent.override(model=model):
        # Each turn gets the next response
        await space.run(...)
"""

from typing import Any

from pydantic_ai import AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel


def create_multi_turn_model(responses: list[str | list[Any]]) -> FunctionModel:
    """Create FunctionModel that returns different responses each turn.

    Useful for testing multi-turn conversations where each turn needs
    a specific response. Supports both text responses and complex parts.

    Args:
        responses: List of responses, one per turn. Each response can be:
            - str: Returns TextPart with that content
            - list[TextPart | ToolCallPart]: Returns those parts

    Returns:
        FunctionModel instance

    Example:
        # Simple text responses
        model = create_multi_turn_model(["First", "Second", "Third"])

        # Mix of text and tool calls
        model = create_multi_turn_model([
            [ToolCallPart.from_raw_args("get_weather", {"city": "London"})],
            ["The weather is sunny"],
        ])

    Note:
        If more turns occur than responses provided, the last response repeats.
    """
    turn = 0

    def response_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal turn
        # Get response for this turn (or last response if out of bounds)
        response = responses[min(turn, len(responses) - 1)]
        turn += 1

        # Convert string to TextPart, otherwise assume it's already Parts
        if isinstance(response, str):
            parts = [TextPart(content=response)]
        else:
            parts = response

        return ModelResponse(parts=parts)

    return FunctionModel(response_function)


def create_tool_calling_model(
    tool_name: str, tool_args: dict, result_text: str = "Done"
) -> FunctionModel:
    """Create FunctionModel that calls a specific tool once, then returns text.

    Useful for testing tool execution flow: agent calls tool, receives result,
    then responds with text.

    Args:
        tool_name: Tool function name to call
        tool_args: Tool arguments dict
        result_text: Text response after tool executes (default: "Done")

    Returns:
        FunctionModel instance

    Example:
        model = create_tool_calling_model(
            "get_weather",
            {"city": "London"},
            "It's sunny"
        )

        # First agent turn: calls get_weather tool
        # Second agent turn: responds with "It's sunny"

    Note:
        The tool must be registered on the agent for this to work.
        The model will call it on first turn, then respond with text on second turn.
    """
    called = False

    def response_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal called
        if not called:
            called = True
            return ModelResponse(parts=[ToolCallPart.from_raw_args(tool_name, tool_args)])
        else:
            return ModelResponse(parts=[TextPart(content=result_text)])

    return FunctionModel(response_function)


def create_agent_switching_model(
    target_agent: str, follow_up_text: str = "Switched agents"
) -> FunctionModel:
    """Create FunctionModel that triggers agent switch mutation.

    CRITICAL for testing multi-agent orchestration without live LLM calls.
    The model will call the switch_active_agent tool, which triggers
    the agent switching mutation in RosterSpace.

    Args:
        target_agent: Agent identifier to switch to
        follow_up_text: Text response after switch (default: "Switched agents")

    Returns:
        FunctionModel instance

    Example:
        # Test RosterSpace agent switching
        model = create_agent_switching_model("unreal-engine-expert")

        roster_space = RosterSpace(agents=[jarvis, unreal])
        state = ThreadState(thread_id=uuid4(), active_space=roster_space)

        with roster_space.active_agent.override(model=model):
            await graph.run(UserInput("Switch to Unreal"), state, deps)

        # After execution, active agent should be unreal
        assert roster_space.active_agent.identifier == "unreal-engine-expert"

    Note:
        The switch_active_agent tool must be registered on the Space.
        This is the standard tool provided by RosterSpace and other multi-agent spaces.
    """
    called = False

    def response_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal called
        if not called:
            called = True
            return ModelResponse(
                parts=[
                    ToolCallPart.from_raw_args(
                        "switch_active_agent", {"agent_identifier": target_agent}
                    )
                ]
            )
        else:
            return ModelResponse(parts=[TextPart(content=follow_up_text)])

    return FunctionModel(response_function)


def create_conditional_model(
    condition_fn: callable, true_response: str | list[Any], false_response: str | list[Any]
) -> FunctionModel:
    """Create FunctionModel that returns different responses based on a condition.

    Useful for testing conditional logic, like responding differently based on
    message history or agent context.

    Args:
        condition_fn: Function that takes (messages, info) and returns bool
        true_response: Response if condition is True (str or list of Parts)
        false_response: Response if condition is False (str or list of Parts)

    Returns:
        FunctionModel instance

    Example:
        # Respond differently if user mentioned "urgent"
        model = create_conditional_model(
            lambda msgs, info: any("urgent" in str(m) for m in msgs),
            "This is urgent, acting now!",
            "Processing normally"
        )
    """

    def response_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        response = true_response if condition_fn(messages, info) else false_response

        # Convert string to TextPart
        if isinstance(response, str):
            parts = [TextPart(content=response)]
        else:
            parts = response

        return ModelResponse(parts=parts)

    return FunctionModel(response_function)
