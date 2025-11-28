"""Transform ThreadProtocol events to Pydantic AI ModelMessages.

This implements the generic/default transformation with minimal opinions.
Events are transformed nearly verbatim, doing only what's required for
compatibility with Pydantic AI's ModelMessage format.

v0.0.7: ThreadProtocol is condensed VSP v6 format. Custom events use data-* prefix.
"""

from datetime import datetime
from uuid import UUID

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    RequestUsage,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolResults, ToolApproved, ToolDenied

from chimera_core.protocols.transformer import ThreadProtocolTransformer
from chimera_core.types.user_input import UserInput


class EmptyTransformer(ThreadProtocolTransformer):
    """Transformer that returns empty message history for stateless execution.

    Use cases:
    - Graph/FSM nodes that should only see current state, not full history
    - Stateless agents that don't need conversation history
    - Reducing token usage when history isn't needed
    - Testing agents in isolation

    Each agent turn starts with a clean slate, seeing only the current message
    and system prompt, with no context from previous turns.
    """

    def transform(self, events: list[dict], agent_id: UUID | None = None) -> list[ModelMessage]:
        """Return empty message history.

        Args:
            events: List of ThreadProtocol events (ignored)
            agent_id: Agent perspective (ignored)

        Returns:
            Empty list - no message history
        """
        return []

    def build_deferred_tool_results(
        self, events: list[dict], user_input: UserInput | None = None
    ) -> DeferredToolResults | None:
        """Build DeferredToolResults from user approval/denial data.

        Tool approval is independent of conversation history - even stateless
        nodes can require human-in-the-loop tool approval.

        Args:
            events: ThreadProtocol events (ignored for stateless transformer)
            user_input: User input dict with kind="deferred_tools"

        Returns:
            DeferredToolResults if user_input contains deferred data, None otherwise
        """
        if not user_input:
            return None

        # Check if this is deferred tools input
        if user_input.kind != "deferred_tools":
            return None

        results = DeferredToolResults()

        # Process approvals
        approvals = user_input.approvals
        for tool_call_id, decision in approvals.items():
            if isinstance(decision, bool):
                # Simple boolean approval/denial
                results.approvals[tool_call_id] = decision
            elif isinstance(decision, dict):
                # Complex approval with optional message or override args
                approved = decision.get("approved", True)
                if approved is False:
                    # Denial with custom message
                    message = decision.get("message", "User denied this action")
                    results.approvals[tool_call_id] = ToolDenied(message=message)
                else:
                    # Approval with optional override args
                    override_args = decision.get("override_args")
                    results.approvals[tool_call_id] = ToolApproved(override_args=override_args)

        # Process external tool call results
        calls = user_input.calls
        for tool_call_id, result in calls.items():
            results.calls[tool_call_id] = result

        return results


class GenericTransformer(ThreadProtocolTransformer):
    """Default transformer with minimal transformation.

    This implements the generic flow:
    - Nearly verbatim mapping
    - No agent name prefixes
    - No filtering or hiding
    - Respects turn boundaries
    """

    def transform(self, events: list[dict], agent_id: UUID | None = None) -> list[ModelMessage]:
        """Transform ThreadProtocol events to ModelMessages.

        Args:
            events: List of ThreadProtocol events (Lines 2+ of JSONL)
            agent_id: Ignored by GenericTransformer (no filtering)

        Returns:
            List of ModelMessage objects for Pydantic AI
        """
        messages: list[ModelMessage] = []
        current_request_parts: list[ModelRequestPart] = []
        current_response_parts: list[ModelResponsePart] = []
        current_usage: RequestUsage | None = None
        has_tool_calls = False  # Track if current response has tool calls

        # Track tool calls to detect incomplete ones (for crash recovery)
        pending_tool_calls: dict[str, ToolCallPart] = {}  # tool_call_id -> ToolCallPart

        for event in events:
            event_type = event.get("type", "")

            # Skip blueprint - it's already processed
            if event_type == "thread-blueprint":
                continue

            # VSP message lifecycle events - skip for now (may use later for message grouping)
            if event_type in ("start", "finish", "pause", "resume"):
                continue

            # Handle turn boundaries (v0.0.7 event names)
            if event_type == "data-user-turn-start":
                current_request_parts = []
                continue
            elif event_type == "data-user-turn-end":
                if current_request_parts:
                    messages.append(ModelRequest(parts=current_request_parts))
                    current_request_parts = []
                continue
            elif event_type == "data-agent-start":
                current_response_parts = []
                current_usage = None
                has_tool_calls = False
                continue
            elif event_type == "data-agent-finish":
                if current_response_parts:
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                continue

            # Handle step boundaries (for multi-step agent turns)
            if event_type == "start-step":
                # Start accumulating for new step
                if current_response_parts:
                    # Save previous step's response
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                    current_usage = None
                    has_tool_calls = False
                continue
            elif event_type == "finish-step":
                # Extract usage if present
                if "usage" in event:
                    usage_data = event["usage"]
                    # Build details dict for extra fields (reasoning_tokens, etc.)
                    details: dict[str, int] = {}
                    if reasoning := usage_data.get("reasoningTokens"):
                        details["reasoning_tokens"] = reasoning
                    current_usage = RequestUsage(
                        input_tokens=usage_data.get("inputTokens", 0),
                        output_tokens=usage_data.get("outputTokens", 0),
                        details=details,
                    )
                continue

            # Transform content events (v0.0.7 format)
            if event_type == "data-user-message":
                # v0.0.7: content is nested in data.content
                content = event.get("data", {}).get("content") or event.get("content", "")
                ts = self._parse_timestamp(event.get("timestamp"))
                part = (
                    UserPromptPart(content=content, timestamp=ts)
                    if ts
                    else UserPromptPart(content=content)
                )
                current_request_parts.append(part)

            elif event_type == "text-complete":
                # v0.0.7: Condensed text event with "content" field
                # GenericTransformer does NO filtering - transforms all events

                # If we have tool calls in current response, flush them first
                # This prevents mixing ToolCallParts and TextParts in same ModelResponse
                if has_tool_calls and current_response_parts:
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                    current_usage = None
                    has_tool_calls = False

                text_content = event["content"]  # v0.0.7: strict "content" field
                text_part = TextPart(content=text_content)
                current_response_parts.append(text_part)

            elif event_type == "reasoning-complete":
                # v0.0.7: Condensed reasoning event with "content" field
                # GenericTransformer does NO filtering

                # If we have tool calls in current response, flush them first
                if has_tool_calls and current_response_parts:
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                    current_usage = None
                    has_tool_calls = False

                reasoning_content = event["content"]  # v0.0.7: strict "content" field
                thinking_part = ThinkingPart(content=reasoning_content)
                current_response_parts.append(thinking_part)

            elif event_type == "tool-input-available":
                # Agent tool call (VSP format)
                # GenericTransformer does NO filtering
                tool_call_id = event.get("toolCallId", "")

                # Skip tool calls with missing/empty tool_call_id (malformed events)
                # LLMs will reject empty tool_call_ids with "tool_call_id  is not found"
                if not tool_call_id or not tool_call_id.strip():
                    continue

                tool_call_part = ToolCallPart(
                    tool_name=event["toolName"],
                    args=event.get("input", {}),
                    tool_call_id=tool_call_id,
                )
                current_response_parts.append(tool_call_part)
                has_tool_calls = True  # Mark that we have tool calls

                # Track this tool call as pending (for crash recovery)
                pending_tool_calls[tool_call_id] = tool_call_part

            elif event_type == "tool-output-available":
                # Tool result - becomes a ModelRequest (VSP format)
                tool_call_id = event.get("toolCallId", "")

                # Skip tool results with missing/empty tool_call_id (malformed events)
                # LLMs will reject empty tool_call_ids with "tool_call_id  is not found"
                if not tool_call_id or not tool_call_id.strip():
                    continue

                # First, flush any pending response (tool calls) before adding tool result
                if current_response_parts:
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                    current_usage = None
                    has_tool_calls = False  # Reset since we flushed the tool calls

                ts = self._parse_timestamp(event.get("timestamp"))
                tool_return_part: ToolReturnPart
                if ts:
                    tool_return_part = ToolReturnPart(
                        tool_name=event["toolName"],
                        content=event.get("output"),
                        tool_call_id=tool_call_id,
                        timestamp=ts,
                    )
                else:
                    tool_return_part = ToolReturnPart(
                        tool_name=event["toolName"],
                        content=event.get("output"),
                        tool_call_id=tool_call_id,
                    )
                # Tool results create new requests
                messages.append(ModelRequest(parts=[tool_return_part]))

                # Mark this tool call as resolved
                if tool_call_id in pending_tool_calls:
                    del pending_tool_calls[tool_call_id]

            elif event_type == "tool-error":
                # Tool error - becomes retry prompt (VSP format)
                tool_call_id = event.get("toolCallId", "")

                # Skip tool errors with missing/empty tool_call_id (malformed events)
                if not tool_call_id or not tool_call_id.strip():
                    continue

                ts = self._parse_timestamp(event.get("timestamp"))
                retry_part: RetryPromptPart
                if ts:
                    retry_part = RetryPromptPart(
                        content=event.get("error", "Tool execution failed"),
                        tool_name=event.get("toolName"),
                        tool_call_id=tool_call_id,
                        timestamp=ts,
                    )
                else:
                    retry_part = RetryPromptPart(
                        content=event.get("error", "Tool execution failed"),
                        tool_name=event.get("toolName"),
                        tool_call_id=tool_call_id,
                    )
                messages.append(ModelRequest(parts=[retry_part]))

                # Mark this tool call as resolved
                if tool_call_id in pending_tool_calls:
                    del pending_tool_calls[tool_call_id]

            # Skip state mutations, approval responses, and system events
            elif event_type == "data-app-chimera":
                continue  # State mutations not part of conversation
            elif event_type == "data-tool-approval-response":
                continue  # Approval decisions documented but not part of ModelMessage history
            elif event_type in {"error", "usage"}:
                continue  # System events handled elsewhere

        # Flush any remaining parts
        if current_request_parts:
            messages.append(ModelRequest(parts=current_request_parts))
        if current_response_parts:
            msg = ModelResponse(parts=current_response_parts)
            if current_usage:
                msg.usage = current_usage
            messages.append(msg)

        # Inject synthetic error responses for any unresolved tool calls
        # This handles cases where execution crashed mid-tool-call
        if pending_tool_calls:
            for tool_call_id, tool_call in pending_tool_calls.items():
                error_part = RetryPromptPart(
                    content=(
                        "Tool execution failed during previous run. "
                        "The tool call did not complete. "
                        "Please try again or use a different approach."
                    ),
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call_id,
                    timestamp=datetime.utcnow(),
                )
                messages.append(ModelRequest(parts=[error_part]))

        return messages

    def _parse_timestamp(self, timestamp_str: str | None) -> datetime | None:
        """Parse ISO timestamp string."""
        if timestamp_str:
            try:
                return datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                pass
        return None

    def add_system_prompt(
        self, messages: list[ModelMessage], system_prompt: str, timestamp: datetime | None = None
    ) -> list[ModelMessage]:
        """Add system prompt as first message if not present.

        Args:
            messages: Existing messages
            system_prompt: System prompt text
            timestamp: Optional timestamp

        Returns:
            Messages with system prompt prepended (if needed)
        """
        # Check if first message already has system prompt
        if messages and isinstance(messages[0], ModelRequest):
            first_parts = messages[0].parts
            if first_parts and isinstance(first_parts[0], SystemPromptPart):
                return messages  # Already has system prompt

        # Create system prompt message
        system_part = SystemPromptPart(
            content=system_prompt, timestamp=timestamp or datetime.utcnow()
        )
        system_msg = ModelRequest(parts=[system_part])

        return [system_msg] + messages

    def build_deferred_tool_results(
        self, events: list[dict], user_input: UserInput | None = None
    ) -> DeferredToolResults | None:
        """Build DeferredToolResults from user approval/denial data.

        Args:
            events: ThreadProtocol events (currently unused, for future context)
            user_input: User input dict with kind="deferred_tools"

        Returns:
            DeferredToolResults if user_input contains deferred data, None otherwise
        """
        if not user_input:
            return None

        # Check if this is deferred tools input
        if user_input.kind != "deferred_tools":
            return None

        results = DeferredToolResults()

        # Process approvals
        approvals = user_input.approvals
        for tool_call_id, decision in approvals.items():
            if isinstance(decision, bool):
                # Simple boolean approval/denial
                results.approvals[tool_call_id] = decision
            elif isinstance(decision, dict):
                # Complex approval with optional message or override args
                approved = decision.get("approved", True)
                if approved is False:
                    # Denial with custom message
                    message = decision.get("message", "User denied this action")
                    results.approvals[tool_call_id] = ToolDenied(message=message)
                else:
                    # Approval with optional override args
                    override_args = decision.get("override_args")
                    results.approvals[tool_call_id] = ToolApproved(override_args=override_args)

        # Process external tool call results
        calls = user_input.calls
        for tool_call_id, result in calls.items():
            results.calls[tool_call_id] = result

        return results
