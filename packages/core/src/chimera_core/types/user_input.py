"""User input types for thread execution.

Discriminated union for different types of user input:
- UserInputMessage: Regular user message
- UserInputDeferredTools: Tool approval/denial responses

This is the single source of truth for user input types.
"""

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field


class UserInputMessage(BaseModel):
    """Standard user message input."""

    kind: Literal["message"] = "message"
    content: str = Field(..., description="User message content")
    client_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Client-specific context. Supported fields:\n"
            "  - cwd: Working directory for file operations\n"
            "  - client_id: Client identifier\n"
            "  - model: Model slug override (e.g. 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet'). "
            "Takes precedence over agent and environment default."
        ),
    )


class UserInputDeferredTools(BaseModel):
    """User input for resuming with deferred tool results.

    This is used when the agent requested tool approval and the user
    is responding with approval/denial decisions.
    """

    kind: Literal["deferred_tools"] = "deferred_tools"
    approvals: Dict[str, Union[bool, Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Map of tool_call_id to approval decision (bool or detailed object)",
    )
    calls: Dict[str, Any] = Field(
        default_factory=dict, description="Map of tool_call_id to external tool execution result"
    )
    client_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Client-specific context. Supported fields:\n"
            "  - cwd: Working directory for file operations\n"
            "  - client_id: Client identifier\n"
            "  - model: Model slug override (e.g. 'openai:gpt-4o', 'anthropic:claude-3-5-sonnet'). "
            "Takes precedence over agent and environment default."
        ),
    )


# Discriminated union - this is what flows through the system
UserInput = Union[UserInputMessage, UserInputDeferredTools]
