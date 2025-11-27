"""Typed application event models for Chimera-specific events.

This module provides type-safe Pydantic models for application-level events
that are not part of the VSP (Vercel AI SDK Stream Protocol).

These events use the data-app-* namespace and are typically marked transient
(not persisted to ThreadProtocol).
"""

from typing import Any, Literal, Union

from .utils import CamelBaseModel

# ==================== CLAUDE CODE WIDGET EVENTS ====================


class ClaudeTextCompletePayload(CamelBaseModel):
    """Payload for text block completion event.

    Emitted when Claude Code completes a text response block.
    """

    index: int
    text: str
    block_type: Literal["text"] = "text"


class ClaudeThinkingCompletePayload(CamelBaseModel):
    """Payload for thinking block completion event.

    Emitted when Claude Code completes an extended thinking block.
    """

    index: int
    thinking: str
    block_type: Literal["thinking"] = "thinking"


class ClaudeToolUseCompletePayload(CamelBaseModel):
    """Payload for tool use completion event.

    Emitted when Claude Code completes a tool call specification.
    """

    index: int
    tool_call_id: str
    tool_name: str
    input: Any  # Tool-specific arguments
    block_type: Literal["tool_use"] = "tool_use"


class ClaudeSessionCompletePayload(CamelBaseModel):
    """Payload for session completion event.

    Emitted when Claude Code session ends (success or error).
    """

    num_turns: int
    duration_ms: int
    total_cost_usd: float
    is_error: bool


# Union of all payload types
ClaudeEventPayload = Union[
    ClaudeTextCompletePayload,
    ClaudeThinkingCompletePayload,
    ClaudeToolUseCompletePayload,
    ClaudeSessionCompletePayload,
]


class ClaudeEventData(CamelBaseModel):
    """Data structure for data-app-claude events.

    Contains source identifier, session ID, event type, and typed payload.
    """

    source: str  # Format: "widget:ClaudeCodeWidget:{instance_id}"
    claude_session_id: str
    event_type: Literal[
        "text-complete", "thinking-complete", "tool-use-complete", "session-complete"
    ]
    payload: ClaudeEventPayload


class DataAppClaudeEvent(CamelBaseModel):
    """Complete data-app-claude event structure.

    These events provide real-time visibility into Claude Code execution
    and are marked transient (not persisted to ThreadProtocol).

    Example:
        >>> event = DataAppClaudeEvent(
        ...     type="data-app-claude",
        ...     transient=True,
        ...     data=ClaudeEventData(
        ...         source="widget:ClaudeCodeWidget:abc123",
        ...         claude_session_id="session-xyz",
        ...         event_type="text-complete",
        ...         payload=ClaudeTextCompletePayload(
        ...             index=0,
        ...             text="Hello world",
        ...             block_type="text"
        ...         )
        ...     )
        ... )
    """

    type: Literal["data-app-claude"] = "data-app-claude"
    transient: bool = True
    data: ClaudeEventData


# ==================== TYPE GUARDS ====================


def is_claude_text_complete(event: dict) -> bool:
    """Check if event is a text-complete event."""
    return (
        event.get("type") == "data-app-claude"
        and event.get("data", {}).get("eventType") == "text-complete"
    )


def is_claude_thinking_complete(event: dict) -> bool:
    """Check if event is a thinking-complete event."""
    return (
        event.get("type") == "data-app-claude"
        and event.get("data", {}).get("eventType") == "thinking-complete"
    )


def is_claude_tool_use_complete(event: dict) -> bool:
    """Check if event is a tool-use-complete event."""
    return (
        event.get("type") == "data-app-claude"
        and event.get("data", {}).get("eventType") == "tool-use-complete"
    )


def is_claude_session_complete(event: dict) -> bool:
    """Check if event is a session-complete event."""
    return (
        event.get("type") == "data-app-claude"
        and event.get("data", {}).get("eventType") == "session-complete"
    )
