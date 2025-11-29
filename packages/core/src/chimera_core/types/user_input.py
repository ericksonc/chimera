"""User input types for thread execution.

Discriminated union for different types of user input:
- UserInputMessage: Regular user message
- UserInputDeferredTools: Tool approval/denial responses
- UserInputScheduled: Triggered/scheduled execution (prompt from config)

This is the single source of truth for user input types.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    """File/image attachment for multimodal user input.

    Supports images and files via data URIs (base64-encoded).
    """

    data_uri: str = Field(
        ...,
        description="Data URI containing the file content (e.g., 'data:image/jpeg;base64,...')",
    )
    media_type: str = Field(
        ...,
        description="MIME type of the attachment (e.g., 'image/jpeg', 'image/png')",
    )
    filename: Optional[str] = Field(
        default=None,
        description="Original filename of the attachment",
    )


class UserInputMessage(BaseModel):
    """Standard user message input with optional attachments."""

    kind: Literal["message"] = "message"
    content: str = Field(..., description="User message content")
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="List of file/image attachments for multimodal input",
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


class UserInputScheduled(BaseModel):
    """Scheduled/triggered execution input.

    The prompt comes from blueprint config, not user interaction.
    Used for cron-triggered agents and other non-interactive execution.
    """

    kind: Literal["scheduled"] = "scheduled"
    prompt: str = Field(..., description="The prompt/instructions for this run")
    trigger_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Context about the trigger (schedule_id, triggered_at, etc.)",
    )


# Discriminated union - this is what flows through the system
UserInput = Union[UserInputMessage, UserInputDeferredTools, UserInputScheduled]
