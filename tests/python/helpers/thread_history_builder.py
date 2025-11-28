"""ThreadHistoryBuilder - Fluent API for creating test event sequences.

This module provides a simple, readable way to construct ThreadProtocol v0.0.7
event sequences for testing without the boilerplate of creating JSONL events manually.

IMPORTANT: Generates ThreadProtocol v0.0.7 JSONL events (data-user-turn-start,
data-agent-start, text-complete, etc.), NOT VSP streaming events.

Example:
    history = (ThreadHistoryBuilder()
        .user_says("What's the weather?")
        .agent_responds("agent-1", "Let me check")
        .agent_calls_tool("agent-1", "get_weather", {"city": "London"}, "Sunny, 22°C")
        .agent_responds("agent-1", "It's sunny and 22°C")
        .build())
"""

from typing import Any, Self
from uuid import uuid4


def create_user_message_events(content: str, user_id: str = "user-1") -> list[dict]:
    """Create ThreadProtocol v0.0.7 events for a user message.

    Generates the event sequence for a user turn:
    - data-user-turn-start: User turn begins
    - data-user-message: User message content
    - data-user-turn-end: User turn ends

    Args:
        content: User message text
        user_id: User identifier (default: "user-1")

    Returns:
        List of ThreadProtocol event dicts
    """
    return [
        {"type": "data-user-turn-start", "data": {"userId": user_id}},
        {"type": "data-user-message", "data": {"content": content}},
        {"type": "data-user-turn-end"},
    ]


def create_agent_response_events(
    agent_id: str, content: str, agent_name: str = "Test"
) -> list[dict]:
    """Create ThreadProtocol v0.0.7 events for an agent text response.

    Generates the event sequence for agent responding with text:
    - data-agent-start: Agent turn begins
    - text-complete: Complete text content
    - data-agent-finish: Agent turn ends

    Args:
        agent_id: Agent identifier
        content: Response text
        agent_name: Agent display name (default: "Test")

    Returns:
        List of ThreadProtocol event dicts
    """
    return [
        {"type": "data-agent-start", "data": {"agentId": agent_id, "agentName": agent_name}},
        {"type": "text-complete", "id": f"text-{uuid4().hex[:8]}", "content": content},
        {"type": "data-agent-finish", "data": {"agentId": agent_id, "agentName": agent_name}},
    ]


def create_tool_call_events(agent_id: str, tool_name: str, args: dict, result: Any) -> list[dict]:
    """Create ThreadProtocol v0.0.7 events for a tool call and result.

    Generates the event sequence for agent calling a tool:
    - tool-input-available: Tool call with args
    - start-step: Step boundary (v0.0.7)
    - tool-output-available: Tool result

    Args:
        agent_id: Agent identifier
        tool_name: Tool function name
        args: Tool arguments dict
        result: Tool return value

    Returns:
        List of ThreadProtocol event dicts
    """
    tool_call_id = f"call_{uuid4().hex[:8]}"

    return [
        {
            "type": "tool-input-available",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "input": args,
        },
        {"type": "start-step"},
        {
            "type": "tool-output-available",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "output": result,
        },
    ]


class ThreadHistoryBuilder:
    """Fluent builder for creating ThreadProtocol event histories.

    Provides a clean, readable API for constructing test event sequences
    without manually creating VSP event dicts.

    Example:
        # Simple conversation
        history = (ThreadHistoryBuilder()
            .user_says("Hi")
            .agent_responds("agent-1", "Hello!")
            .build())

        # Multi-turn with tool use
        history = (ThreadHistoryBuilder()
            .user_says("What's the weather?")
            .agent_responds("agent-1", "Let me check")
            .agent_calls_tool("agent-1", "get_weather", {"city": "London"}, "22°C")
            .agent_responds("agent-1", "It's 22°C in London")
            .build())

    All methods return self for chaining.
    Call .build() to get the final event list.
    """

    def __init__(self):
        """Initialize empty event history."""
        self.events: list[dict] = []

    def user_says(self, content: str) -> Self:
        """Add user message to history.

        Args:
            content: User message text

        Returns:
            Self for chaining
        """
        self.events.extend(create_user_message_events(content))
        return self

    def agent_responds(self, agent_id: str, content: str, agent_name: str = "Test") -> Self:
        """Add agent text response to history.

        Args:
            agent_id: Agent identifier
            content: Response text
            agent_name: Agent display name (default: "Test")

        Returns:
            Self for chaining
        """
        self.events.extend(create_agent_response_events(agent_id, content, agent_name))
        return self

    def agent_calls_tool(self, agent_id: str, tool_name: str, args: dict, result: Any) -> Self:
        """Add tool call and result to history.

        Args:
            agent_id: Agent identifier
            tool_name: Tool function name
            args: Tool arguments dict
            result: Tool return value

        Returns:
            Self for chaining
        """
        self.events.extend(create_tool_call_events(agent_id, tool_name, args, result))
        return self

    def raw_event(self, event: dict) -> Self:
        """Add a raw ThreadProtocol event to history.

        Escape hatch for custom events not covered by helper methods.

        Args:
            event: ThreadProtocol event dict

        Returns:
            Self for chaining
        """
        self.events.append(event)
        return self

    def build(self) -> list[dict]:
        """Return the constructed event list.

        Returns:
            List of ThreadProtocol v0.0.7 event dicts
        """
        return self.events
