"""Typed VSP (Vercel AI SDK Stream Protocol) event models.

This module provides type-safe Pydantic models for all VSP events,
using CamelBaseModel for automatic snake_case → camelCase serialization.

All VSP events are documented at:
meta/designdocs/threadprotocol/reference/concise_vsp.md
"""

from typing import Any, Literal, Optional

from .utils import CamelBaseModel

# ==================== BASE MODEL WITH THREAD SUPPORT ====================


class VSPBaseModel(CamelBaseModel):
    """Base model for all VSP events with optional thread_id support.

    The thread_id field enables multi-thread streaming by allowing events
    to be annotated with their source thread. This is optional for backward
    compatibility with single-thread mode.
    """

    thread_id: Optional[str] = None


# ==================== MESSAGE BOUNDARY EVENTS ====================


class StartEvent(VSPBaseModel):
    """Message start event - marks beginning of assistant response.

    VSP Format: {"type": "start", "messageId": "msg_abc123"}
    """

    type: Literal["start"] = "start"
    message_id: str


class FinishEvent(VSPBaseModel):
    """Message finish event - marks end of assistant response.

    VSP Format: {"type": "finish", "messageId": "msg_abc123"}
    """

    type: Literal["finish"] = "finish"
    message_id: Optional[str] = None


# Note: [DONE] is NOT a JSON event per VSP spec - it's the literal string "data: [DONE]\n\n"
# Stream handlers emit it directly, not as a Pydantic model

# ==================== TEXT PART EVENTS ====================


class TextStartEvent(VSPBaseModel):
    """Text part start event.

    VSP Format: {"type": "text-start", "id": "msg_abc123_text_0", "threadId": "..."}
    """

    type: Literal["text-start"] = "text-start"
    id: str


class TextDeltaEvent(VSPBaseModel):
    """Text content delta event.

    VSP Format: {"type": "text-delta", "id": "msg_abc123_text_0", "delta": "Hello"}

    Note: No threadId on delta events (only boundaries)
    """

    type: Literal["text-delta"] = "text-delta"
    id: str
    delta: str


class TextEndEvent(VSPBaseModel):
    """Text part end event.

    VSP Format: {"type": "text-end", "id": "msg_abc123_text_0", "threadId": "..."}
    """

    type: Literal["text-end"] = "text-end"
    id: str


# ==================== REASONING PART EVENTS ====================


class ReasoningStartEvent(VSPBaseModel):
    """Reasoning/thinking part start event.

    VSP Format: {"type": "reasoning-start", "id": "msg_abc123_thinking_0", "threadId": "..."}
    """

    type: Literal["reasoning-start"] = "reasoning-start"
    id: str


class ReasoningDeltaEvent(VSPBaseModel):
    """Reasoning content delta event.

    VSP Format: {"type": "reasoning-delta", "id": "msg_abc123_thinking_0", "delta": "Let me think..."}

    Note: No threadId on delta events (only boundaries)
    """

    type: Literal["reasoning-delta"] = "reasoning-delta"
    id: str
    delta: str


class ReasoningEndEvent(VSPBaseModel):
    """Reasoning part end event.

    VSP Format: {"type": "reasoning-end", "id": "msg_abc123_thinking_0", "threadId": "..."}
    """

    type: Literal["reasoning-end"] = "reasoning-end"
    id: str


# ==================== TOOL CALL EVENTS ====================


class ToolInputStartEvent(VSPBaseModel):
    """Tool call start event.

    VSP Format: {"type": "tool-input-start", "toolCallId": "call_xyz", "toolName": "search", "threadId": "..."}
    """

    type: Literal["tool-input-start"] = "tool-input-start"
    tool_call_id: str
    tool_name: str


class ToolInputDeltaEvent(VSPBaseModel):
    """Tool call args delta event.

    VSP Format: {"type": "tool-input-delta", "toolCallId": "call_xyz", "inputTextDelta": "{\"query\":"}

    Note: No threadId on delta events (only boundaries)
    """

    type: Literal["tool-input-delta"] = "tool-input-delta"
    tool_call_id: str
    input_text_delta: str


class ToolInputAvailableEvent(VSPBaseModel):
    """Tool call ready to execute event.

    VSP Format: {
        "type": "tool-input-available",
        "toolCallId": "call_xyz",
        "toolName": "search",
        "input": {"query": "test"},
        "timestamp": "2025-01-01T00:00:00Z",
        "threadId": "..."
    }
    """

    type: Literal["tool-input-available"] = "tool-input-available"
    tool_call_id: str
    tool_name: str
    input: Any  # Tool-specific args dict
    timestamp: str


class ToolOutputAvailableEvent(VSPBaseModel):
    """Tool execution result event.

    VSP Format: {
        "type": "tool-output-available",
        "toolCallId": "call_xyz",
        "toolName": "search",
        "output": "Result text",
        "timestamp": "2025-01-01T00:00:00Z",
        "threadId": "..."
    }
    """

    type: Literal["tool-output-available"] = "tool-output-available"
    tool_call_id: str
    tool_name: str
    output: Any  # Tool-specific result
    timestamp: str


class ToolOutputDeniedEvent(VSPBaseModel):
    """Tool execution denied event.

    VSP Format: {"type": "tool-output-denied", "toolCallId": "call_xyz", "threadId": "..."}
    """

    type: Literal["tool-output-denied"] = "tool-output-denied"
    tool_call_id: str


class ToolApprovalRequestEvent(VSPBaseModel):
    """Tool approval request event.

    VSP Format: {
        "type": "tool-approval-request",
        "approvalId": "appr_123",
        "toolCallId": "call_xyz",
        "threadId": "..."
    }
    """

    type: Literal["tool-approval-request"] = "tool-approval-request"
    approval_id: str
    tool_call_id: str


# ==================== STEP BOUNDARY EVENTS ====================


class StartStepEvent(VSPBaseModel):
    """Step start event - marks beginning of tool execution phase.

    VSP Format: {"type": "start-step"}
    """

    type: Literal["start-step"] = "start-step"


class FinishStepEvent(VSPBaseModel):
    """Step finish event - marks end of model processing.

    VSP Format: {"type": "finish-step"}
    """

    type: Literal["finish-step"] = "finish-step"


# ==================== ERROR EVENT ====================


class ErrorEvent(VSPBaseModel):
    """Error event - emitted when stream fails.

    VSP Format: {"type": "error", "errorText": "Something went wrong"}
    """

    type: Literal["error"] = "error"
    error_text: str


# ==================== THREAD LIFECYCLE EVENTS ====================


class DataThreadStartEvent(VSPBaseModel):
    """Thread start event - marks beginning of multi-thread execution.

    Custom event for multi-thread streaming. Emitted when a thread begins execution.
    thread_id inherited from VSPBaseModel.

    Format: {"type": "data-thread-start", "threadId": "thread-1"}
    """

    type: Literal["data-thread-start"] = "data-thread-start"


class DataThreadFinishEvent(VSPBaseModel):
    """Thread finish event - marks end of multi-thread execution.

    Custom event for multi-thread streaming. Emitted when a thread completes execution.
    thread_id inherited from VSPBaseModel.

    Format: {"type": "data-thread-finish", "threadId": "thread-1"}
    """

    type: Literal["data-thread-finish"] = "data-thread-finish"


# ==================== CHIMERA APP USAGE EVENT ====================


class ChimeraAppUsageEvent(VSPBaseModel):
    """Chimera app usage event - emitted after each model request with token usage.

    Custom event for Chimera applications to track per-API-call token usage.
    Emitted as soon as usage data becomes available from the model response.
    thread_id inherited from VSPBaseModel.

    Format: {
        "type": "chimera-app-usage",
        "messageId": "msg_abc123",
        "inputTokens": 100,
        "outputTokens": 50,
        "cacheWriteTokens": 0,
        "cacheReadTokens": 500,
        "totalTokens": 150,
        "details": {"reasoning_tokens": 448},
        "threadId": "thread-1"
    }
    """

    type: Literal["chimera-app-usage"] = "chimera-app-usage"
    message_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    input_audio_tokens: int = 0
    cache_audio_read_tokens: int = 0
    output_audio_tokens: int = 0
    total_tokens: int = 0
    details: Optional[dict[str, int]] = None


# ==================== TYPE UNIONS ====================

# Union of all VSP event types
VSPEvent = (
    StartEvent
    | FinishEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ReasoningStartEvent
    | ReasoningDeltaEvent
    | ReasoningEndEvent
    | ToolInputStartEvent
    | ToolInputDeltaEvent
    | ToolInputAvailableEvent
    | ToolOutputAvailableEvent
    | ToolOutputDeniedEvent
    | ToolApprovalRequestEvent
    | StartStepEvent
    | FinishStepEvent
    | ErrorEvent
    | DataThreadStartEvent
    | DataThreadFinishEvent
    | ChimeraAppUsageEvent
)

# Events that include threadId
VSPBoundaryEvent = (
    StartEvent
    | FinishEvent
    | TextStartEvent
    | TextEndEvent
    | ReasoningStartEvent
    | ReasoningEndEvent
    | ToolInputStartEvent
    | ToolInputAvailableEvent
    | ToolOutputAvailableEvent
    | ToolOutputDeniedEvent
    | ToolApprovalRequestEvent
    | ChimeraAppUsageEvent
)

# Events that do NOT include threadId (delta events only)
VSPDeltaEvent = TextDeltaEvent | ReasoningDeltaEvent | ToolInputDeltaEvent
