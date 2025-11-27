"""Kimi K2 model adapter with tool ID normalization.

Kimi K2 models require tool IDs in conversation history to follow the
`functions.{func_name}:{idx}` format, even though the OpenAI-compatible API
returns IDs without the "functions." prefix.

This adapter wraps OpenAIChatModel to normalize tool IDs when sending
messages back to the model, preventing the infinite thinking loops that
occur when historical tool IDs are malformed.

See: _meta/agents/blueprints/kimi-k2.md for details on the issue.
"""

from openai.types.chat import ChatCompletionMessageFunctionToolCallParam
from pydantic_ai.messages import (
    ModelMessage,
    ToolCallPart,
)
from pydantic_ai.models.openai import OpenAIChatModel


class KimiChatModel(OpenAIChatModel):
    """OpenAI-compatible chat model wrapper for Kimi K2 with tool ID normalization.

    Extends OpenAIChatModel to automatically normalize tool call IDs to Kimi's
    expected format: `functions.{tool_name}:{index}`

    This prevents the model from getting confused about conversation state,
    which manifests as:
    - Infinite thinking loops
    - Exposed internal control tokens (<think> tags)
    - Failure to transition from thinking to tool calling
    """

    @staticmethod
    def normalize_tool_id_for_kimi(tool_id: str, tool_name: str) -> str:
        """Normalize a tool ID to Kimi K2's expected format.

        Kimi expects: `functions.{tool_name}:{index}`

        Args:
            tool_id: Original tool ID (e.g., "message_claude_code:0", "call_abc123")
            tool_name: The function name for this tool

        Returns:
            Normalized tool ID with "functions." prefix
        """
        # Already in correct format
        if tool_id.startswith("functions."):
            return tool_id

        # Has :idx format - preserve index
        if ":" in tool_id:
            name_part, idx = tool_id.rsplit(":", 1)
            # Use the tool_name parameter if name doesn't match
            # (this handles cases where ID is generic like "call_123")
            if name_part == tool_name:
                return f"functions.{name_part}:{idx}"
            else:
                return f"functions.{tool_name}:{idx}"

        # OpenAI format (call_xxx) or other - default to index 0
        # In practice this shouldn't happen with Kimi, but handle gracefully
        return f"functions.{tool_name}:0"

    @staticmethod
    def _map_tool_call(t: ToolCallPart) -> ChatCompletionMessageFunctionToolCallParam:
        """Map a ToolCallPart to OpenAI format with normalized Kimi tool ID.

        Overrides OpenAIChatModel._map_tool_call to add "functions." prefix
        to tool IDs when sending back to Kimi.
        """
        from pydantic_ai._utils import guard_tool_call_id

        # Get the original ID (with fallback if None)
        original_id = guard_tool_call_id(t=t)

        # Normalize for Kimi
        normalized_id = KimiChatModel.normalize_tool_id_for_kimi(original_id, t.tool_name)

        return ChatCompletionMessageFunctionToolCallParam(
            id=normalized_id,
            type="function",
            function={"name": t.tool_name, "arguments": t.args_as_json_str()},
        )

    async def _map_messages(self, messages: list[ModelMessage]) -> list:
        """Map messages with tool ID normalization for Kimi K2.

        Overrides to normalize tool IDs in:
        - ToolReturnPart (tool results from history)
        - RetryPromptPart (retry prompts with tool context)
        """
        # First get the standard OpenAI message mapping
        openai_messages = await super()._map_messages(messages)

        # Now post-process to normalize tool IDs in tool result messages
        # This ensures historical tool calls have the correct format
        for msg in openai_messages:
            # Tool result messages have role='tool'
            if isinstance(msg, dict) and msg.get("role") == "tool":
                tool_call_id = msg.get("tool_call_id")
                tool_name = msg.get("name")

                if tool_call_id and tool_name:
                    msg["tool_call_id"] = self.normalize_tool_id_for_kimi(tool_call_id, tool_name)

        return openai_messages
