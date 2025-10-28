"""Transform ThreadProtocol events to Pydantic AI ModelMessages.

This implements the generic/default transformation with minimal opinions.
Events are transformed nearly verbatim, doing only what's required for
compatibility with Pydantic AI's ModelMessage format.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    RetryPromptPart,
    SystemPromptPart,
    RequestUsage
)

from core.protocols.transformer import ThreadProtocolTransformer


class GenericTransformer(ThreadProtocolTransformer):
    """Default transformer with minimal transformation.

    This implements the generic flow:
    - Nearly verbatim mapping
    - No agent name prefixes
    - No filtering or hiding
    - Respects turn boundaries
    """

    def transform(
        self,
        events: list[dict],
        agent_id: UUID | None = None
    ) -> list[ModelMessage]:
        """Transform ThreadProtocol events to ModelMessages.

        Args:
            events: List of ThreadProtocol events (Lines 2+ of JSONL)
            agent_id: If specified, filter to only this agent's perspective

        Returns:
            List of ModelMessage objects for Pydantic AI
        """
        messages = []
        current_request_parts = []
        current_response_parts = []
        current_usage = None
        in_user_turn = False
        in_agent_turn = False

        for event in events:
            event_type = event.get("event_type", "")

            # Skip blueprint - it's already processed
            if event_type == "thread_blueprint":
                continue

            # Handle turn boundaries
            if event_type == "user_turn_start":
                in_user_turn = True
                current_request_parts = []
                continue
            elif event_type == "user_turn_end":
                if current_request_parts:
                    messages.append(ModelRequest(parts=current_request_parts))
                    current_request_parts = []
                in_user_turn = False
                continue
            elif event_type == "agent_turn_start":
                in_agent_turn = True
                current_response_parts = []
                current_usage = None
                continue
            elif event_type == "agent_turn_end":
                if current_response_parts:
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                in_agent_turn = False
                continue

            # Handle step boundaries (for multi-step agent turns)
            if event_type == "step_start":
                # Start accumulating for new step
                if current_response_parts:
                    # Save previous step's response
                    msg = ModelResponse(parts=current_response_parts)
                    if current_usage:
                        msg.usage = current_usage
                    messages.append(msg)
                    current_response_parts = []
                    current_usage = None
                continue
            elif event_type == "step_end":
                # Extract usage if present
                if "usage" in event:
                    usage_data = event["usage"]
                    current_usage = RequestUsage(
                        input_tokens=usage_data.get("input_tokens", 0),
                        output_tokens=usage_data.get("output_tokens", 0),
                        reasoning_tokens=usage_data.get("reasoning_tokens", 0),
                        total_tokens=(
                            usage_data.get("input_tokens", 0) +
                            usage_data.get("output_tokens", 0)
                        )
                    )
                continue

            # Transform content events
            if event_type == "user_message":
                part = UserPromptPart(
                    content=event["content"],
                    timestamp=self._parse_timestamp(event.get("timestamp"))
                )
                if in_user_turn:
                    current_request_parts.append(part)
                else:
                    # Standalone user message
                    messages.append(ModelRequest(parts=[part]))

            elif event_type == "text":
                # Agent text response
                if agent_id and event.get("agent_id") != str(agent_id):
                    continue  # Skip if filtering by agent
                part = TextPart(content=event["content"])
                if in_agent_turn:
                    current_response_parts.append(part)
                else:
                    messages.append(ModelResponse(parts=[part]))

            elif event_type == "thinking":
                # Agent thinking (o1 models)
                if agent_id and event.get("agent_id") != str(agent_id):
                    continue
                # For MVP, we'll treat thinking as text
                # In future, use ThinkingPart when Pydantic AI supports it
                part = TextPart(content=f"[Thinking] {event['content']}")
                if in_agent_turn:
                    current_response_parts.append(part)
                else:
                    messages.append(ModelResponse(parts=[part]))

            elif event_type == "tool_call":
                # Agent tool call
                if agent_id and event.get("agent_id") != str(agent_id):
                    continue
                part = ToolCallPart(
                    tool_name=event["tool_name"],
                    args=event.get("args", {}),
                    tool_call_id=event.get("tool_call_id", "")
                )
                if in_agent_turn:
                    current_response_parts.append(part)
                else:
                    messages.append(ModelResponse(parts=[part]))

            elif event_type == "tool_result":
                # Tool result - becomes a ModelRequest
                part = ToolReturnPart(
                    tool_name=event["tool_name"],
                    content=event.get("result"),
                    tool_call_id=event.get("tool_call_id", ""),
                    timestamp=self._parse_timestamp(event.get("timestamp"))
                )
                # Tool results create new requests
                messages.append(ModelRequest(parts=[part]))

            elif event_type == "tool_error":
                # Tool error - becomes retry prompt
                part = RetryPromptPart(
                    content=event.get("error", "Tool execution failed"),
                    tool_name=event.get("tool_name"),
                    tool_call_id=event.get("tool_call_id", ""),
                    timestamp=self._parse_timestamp(event.get("timestamp"))
                )
                messages.append(ModelRequest(parts=[part]))

            # Skip state mutations and system events
            elif event_type == "data-app-chimera":
                continue  # State mutations not part of conversation
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
        self,
        messages: list[ModelMessage],
        system_prompt: str,
        timestamp: datetime | None = None
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
            content=system_prompt,
            timestamp=timestamp or datetime.utcnow()
        )
        system_msg = ModelRequest(parts=[system_part])

        return [system_msg] + messages