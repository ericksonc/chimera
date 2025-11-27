"""BaseMultiAgentTransformer - Opinionated transformer for multi-agent spaces.

This transformer extends GenericTransformer with multi-agent awareness:
- Adds agent name prefixes to text messages from other agents
- [DISABLED] Simplifies other agents' tool calls to text summaries (was confusing agents)
- [DISABLED] Hides failed tool calls from other agents (was confusing agents)
- Shows all tool calls in full detail to all agents
"""

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    # UserPromptPart,  # No longer needed - tool return simplification disabled
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from chimera_core.protocols.transformer import ThreadProtocolTransformer
from chimera_core.threadprotocol.transformer import GenericTransformer


class BaseMultiAgentTransformer(ThreadProtocolTransformer):
    """Multi-agent aware transformer with agent name prefixes.

    This transformer provides opinionated multi-agent behavior:
    1. Text messages from other agents are prefixed with "(Agent: {name}) - "
    2. All tool calls: Full ModelMessage structure shown to all agents

    NOTE: Previously simplified other agents' tool calls to text descriptions,
    but this confused agents into thinking they should output text like
    "Agent X used tool Y" instead of actually using tools. Tool call
    transformation is now disabled.
    """

    if TYPE_CHECKING:
        from chimera_core.agent import Agent

    def __init__(self, agents_by_identifier: dict[str, "Agent"]):
        """Initialize with agent identifier to Agent mapping.

        Args:
            agents_by_identifier: Dictionary mapping agent string identifiers to Agent instances
                                 (e.g., "jarvis-basic", "analyst-pro")
        """
        self.agents_by_identifier = agents_by_identifier
        self.generic_transformer = GenericTransformer()

    def transform(self, events: list[dict], agent_id: UUID | None = None) -> list[ModelMessage]:
        """Transform ThreadProtocol events with multi-agent awareness.

        This method delegates to GenericTransformer for all event parsing
        (getting v0.0.7 support, crash recovery, empty tool_call_id filtering, etc.),
        then applies multi-agent transformations to the resulting ModelMessages.

        Args:
            events: List of ThreadProtocol events (Lines 2+ of JSONL)
            agent_id: Current agent's perspective (for filtering/formatting)

        Returns:
            List of ModelMessage objects for Pydantic AI with multi-agent formatting
        """
        # Step 1: Get clean ModelMessages from GenericTransformer
        # This handles all the v0.0.7 parsing, crash recovery, etc.
        base_messages = self.generic_transformer.transform(events, agent_id=None)

        # Step 2: Apply multi-agent transformations to those ModelMessages
        # This adds agent name prefixes, simplifies other agents' tool calls, etc.
        formatted_messages = self._apply_multi_agent_formatting(
            events=events,  # For building ownership maps
            messages=base_messages,  # Transform these
            current_agent_id=str(agent_id) if agent_id else None,
        )

        return formatted_messages

    def _apply_multi_agent_formatting(
        self, events: list[dict], messages: list[ModelMessage], current_agent_id: Optional[str]
    ) -> list[ModelMessage]:
        """Apply multi-agent specific formatting to messages.

        This method transforms ModelMessages from GenericTransformer by:
        1. Adding agent name prefixes to text from other agents
        2. [DISABLED] Simplifying other agents' tool calls to text descriptions
        3. [DISABLED] Hiding failed tool calls from other agents

        Args:
            events: Original ThreadProtocol events (for building ownership maps)
            messages: Base ModelMessages from GenericTransformer
            current_agent_id: String identifier of the current agent (for filtering)

        Returns:
            List of formatted ModelMessages
        """
        # Build ownership maps from events
        tool_call_owners = {}  # tool_call_id -> agent_id
        response_agent_map = []  # List of agent_ids for each ModelResponse

        current_turn_agent = None

        for event in events:
            event_type = event.get("type", "")

            # Track agent turn boundaries (v0.0.7 format)
            if event_type in ("data-agent-start", "agent-turn-start"):
                # v0.0.7: agent_id in data.agentId; v0.0.6: agent_id in agentId
                current_turn_agent = event.get("data", {}).get("agentId") or event.get("agentId")
            elif event_type in ("data-agent-finish", "agent-turn-end"):
                # Mark the end of this agent's response
                if current_turn_agent:
                    response_agent_map.append(current_turn_agent)
                current_turn_agent = None

            # Track tool call ownership (v0.0.7 format)
            # In v0.0.7, tool calls appear as "tool-call" events during agent turns
            elif event_type in ("tool-call", "tool-input-available"):
                # v0.0.7: toolCall.id; v0.0.6: toolCallId
                tool_call_id = event.get("toolCall", {}).get("id") or event.get("toolCallId")
                if tool_call_id and current_turn_agent:
                    tool_call_owners[tool_call_id] = current_turn_agent

        # Handle step boundaries - each finish-step creates a ModelResponse
        # Walk events again to count step-based responses
        step_agent_map = []
        current_step_agent = None

        for event in events:
            event_type = event.get("type", "")

            if event_type in ("data-agent-start", "agent-turn-start"):
                current_step_agent = event.get("data", {}).get("agentId") or event.get("agentId")
            elif event_type == "finish-step":
                # Each finish-step creates a ModelResponse
                if current_step_agent:
                    step_agent_map.append(current_step_agent)
            elif event_type in ("data-agent-finish", "agent-turn-end"):
                # Final response at end of turn
                if current_step_agent:
                    step_agent_map.append(current_step_agent)
                current_step_agent = None

        # Use whichever map has more entries (handles both step-based and turn-based responses)
        final_agent_map = (
            step_agent_map if len(step_agent_map) >= len(response_agent_map) else response_agent_map
        )

        # Now transform messages using the ownership maps
        formatted_messages = []
        response_index = 0

        for msg in messages:
            if isinstance(msg, ModelResponse):
                # Get the agent who created this response
                owner_agent_id = (
                    final_agent_map[response_index]
                    if response_index < len(final_agent_map)
                    else None
                )
                response_index += 1

                new_parts = []
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        # Add agent name prefix if from another agent
                        if owner_agent_id and owner_agent_id != current_agent_id:
                            agent_name = self._get_agent_name(owner_agent_id)
                            prefixed_content = f"(Agent: {agent_name}) - {part.content}"
                            new_parts.append(TextPart(content=prefixed_content))
                        else:
                            new_parts.append(part)

                    elif isinstance(part, ToolCallPart):
                        # DISABLED: Tool call simplification was confusing agents
                        # They would mimic the text output instead of using tools
                        # # Check ownership and simplify if from another agent
                        # tool_owner = tool_call_owners.get(part.tool_call_id)
                        # if tool_owner and tool_owner != current_agent_id:
                        #     # Simplify to text description
                        #     agent_name = self._get_agent_name(tool_owner)
                        #     simplified_text = f"Agent {agent_name} used tool {part.tool_name}"
                        #     new_parts.append(TextPart(content=simplified_text))
                        # else:
                        #     # Keep full tool call for current agent
                        #     new_parts.append(part)

                        # Now: Always keep full tool call structure for all agents
                        new_parts.append(part)

                    else:
                        # Pass through other part types unchanged
                        new_parts.append(part)

                # Preserve usage metadata if present
                new_msg = ModelResponse(parts=new_parts)
                if hasattr(msg, "usage") and msg.usage:
                    new_msg.usage = msg.usage
                formatted_messages.append(new_msg)

            elif isinstance(msg, ModelRequest):
                # DISABLED: Tool return/error simplification was confusing agents
                # Filter/transform tool-related parts in requests
                new_parts = []
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        # DISABLED: Return simplification was confusing agents
                        # # Check ownership
                        # tool_owner = tool_call_owners.get(part.tool_call_id)
                        # if tool_owner and tool_owner != current_agent_id:
                        #     # Simplify to text
                        #     agent_name = self._get_agent_name(tool_owner)
                        #     simplified_text = f"Agent {agent_name} successfully used {part.tool_name}"
                        #     new_parts.append(UserPromptPart(content=simplified_text))
                        # else:
                        #     # Keep full tool return for current agent
                        #     new_parts.append(part)

                        # Now: Always keep full tool return for all agents
                        new_parts.append(part)

                    elif isinstance(part, RetryPromptPart):
                        # DISABLED: Error filtering was confusing agents
                        # # Only show errors to the agent that made the call
                        # if part.tool_call_id:
                        #     tool_owner = tool_call_owners.get(part.tool_call_id)
                        #     # Show if current agent owns it, or if owner unknown (safe default)
                        #     if tool_owner == current_agent_id or not tool_owner:
                        #         new_parts.append(part)
                        # else:
                        #     # No tool_call_id means it's a general error - show it
                        #     new_parts.append(part)

                        # Now: Always show all errors to all agents
                        new_parts.append(part)

                    else:
                        # Pass through user prompts, system prompts, etc.
                        new_parts.append(part)

                # Only add the request if it has parts
                if new_parts:
                    formatted_messages.append(ModelRequest(parts=new_parts))

            else:
                # Pass through any other message types unchanged
                formatted_messages.append(msg)

        return formatted_messages

    def _get_agent_name(self, agent_id: Optional[str]) -> str:
        """Get agent name from identifier.

        Args:
            agent_id: Agent string identifier (e.g., "jarvis-basic", "analyst-pro")

        Returns:
            Agent name, or "Unknown" if not found
        """
        if not agent_id:
            return "Unknown"

        agent = self.agents_by_identifier.get(agent_id)
        if agent:
            return agent.name
        return "Unknown"
