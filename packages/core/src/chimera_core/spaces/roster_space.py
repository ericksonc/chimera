"""RosterSpace - Multi-agent space with tool-based agent switching.

RosterSpace allows agents to switch control to other agents in the roster
by calling the change_agent tool. This enables:
- Collaborative multi-agent workflows
- Agent specialization and handoffs
- Dynamic task delegation

The active agent can see all other agents in the roster via ambient context
and switch to any of them using change_agent(identifier).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from chimera_core.spaces.multi_agent_space import AgentSelectionMutation, MultiAgentSpace

# Configure logger
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pydantic_ai.toolsets import FunctionToolset
    from pydantic_graph.beta import StepContext

    from chimera_core.protocols import ReadableThreadState


class RosterSpace(MultiAgentSpace):
    """Multi-agent space with tool-based agent switching.

    Features:
    - change_agent tool for switching between agents
    - Ambient context showing all available agents
    - Dynamic validation (can only switch to other agents, not current)
    - Full conversation history visible to all agents (via BaseMultiAgentTransformer)

    Example usage:
        # Create agents
        alice = Agent(id=uuid4(), name="Alice", base_prompt="...", identifier="alice")
        bob = Agent(id=uuid4(), name="Bob", base_prompt="...", identifier="bob")

        # Create roster space
        roster = RosterSpace()
        roster._agents = [alice, bob]
        roster._active_agent_identifier = "alice"

        # Alice can now call change_agent("bob") to hand off to Bob
    """

    def _get_all_agents(self):
        """Get all agents in this space.

        Returns:
            List of all agents in the roster
        """
        return self._agents

    # ========================================================================
    # Tool Registration - change_agent Tool
    # ========================================================================

    def get_toolset(self, ctx: "StepContext") -> Optional["FunctionToolset"]:
        """Provide the change_agent tool for agent switching.

        Uses Annotated + Field + BeforeValidator for dynamic runtime validation:
        1. Only valid agent identifiers are accepted
        2. Cannot switch to the currently active agent
        3. Pydantic AI automatically validates and retries on invalid values

        Returns:
            FunctionToolset with change_agent tool
        """
        import asyncio
        from typing import Annotated

        from pydantic import BeforeValidator, Field
        from pydantic_ai.toolsets import FunctionToolset

        # Capture emit function AND event loop from context for mutation emission
        # Tools run in worker threads without event loops, so we need to capture the loop now
        self._emit_threadprotocol_event = ctx.deps.emit_threadprotocol_event
        self._event_loop = asyncio.get_running_loop()
        logger.info(
            f"[ROSTER GET_TOOLSET] Captured emit function: {self._emit_threadprotocol_event}"
        )
        logger.info(f"[ROSTER GET_TOOLSET] Captured event loop: {self._event_loop}")

        toolset = FunctionToolset()

        # Build list of valid identifiers (excluding current agent)
        valid_identifiers = [
            agent.identifier
            for agent in self._agents
            if agent.identifier != self._active_agent_identifier
        ]

        if not valid_identifiers:
            # Only one agent in roster, no switching possible
            return None

        # Create validator function
        def validate_agent_identifier(v: str) -> str:
            if v not in valid_identifiers:
                raise ValueError(f"Must be one of: {valid_identifiers}")
            return v

        # Create annotated type with runtime validation
        # The Field's json_schema_extra ensures the model sees valid options
        # The BeforeValidator runs validation and triggers automatic retries on failure
        AgentIdentifier = Annotated[
            str,
            BeforeValidator(validate_agent_identifier),
            Field(
                description="The identifier of the agent to switch to",
                json_schema_extra={"enum": valid_identifiers},
            ),
        ]

        def change_agent(identifier: "AgentIdentifier") -> str:
            """Switch to a different agent in the roster.

            This allows you to delegate the conversation to another agent. Use this tool ONLY if a user has explicitly requested an agent change.

            Args:
                identifier: The identifier of the agent to switch to.

            Returns:
                Confirmation message indicating the switch was successful.
                Note: You still remain "you" for the duration of your "turn."
                This tool only affects which agent will get a turn *after your turn is finished.*
            """
            # Pydantic AI has already validated that identifier is in valid_identifiers

            # Create mutation
            mutation = AgentSelectionMutation(
                new_agent_identifier=identifier,
                reason="tool_call",
                metadata={"requested_by": self._active_agent_identifier},
            )

            # Save to ThreadProtocol, then apply to local state
            self.mutate(mutation)

            # Get the new agent's name for confirmation
            new_agent = self._get_agent_by_identifier(identifier)

            return f"Successfully switched to agent: {new_agent.name} ({identifier})"

        # Make AgentIdentifier available in locals for type evaluation
        change_agent.__annotations__["identifier"] = AgentIdentifier
        toolset.tool(change_agent)

        return toolset

    # ========================================================================
    # Ambient Context - Agent Roster Instructions
    # ========================================================================

    async def get_instructions(self, state: "ReadableThreadState") -> str:
        """Provide detailed agent roster with switching instructions.

        Shows:
        - All available agents (identifier, name, description)
        - Current active agent marked
        - Instructions on how to use change_agent tool

        Args:
            state: Read-only thread state

        Returns:
            Formatted instructions string
        """
        # Only show OTHER agents (not the current one - that's self-evident)
        other_agents = [
            agent for agent in self._agents if agent.identifier != self._active_agent_identifier
        ]

        if not other_agents:
            return ""  # Only one agent, no switching possible

        # Build roster with details
        roster_lines = []
        for agent in other_agents:
            roster_lines.append(f"- **{agent.identifier}**: {agent.name}\n  {agent.description}")

        roster = "\n".join(roster_lines)

        # Build switch instructions
        identifiers = [agent.identifier for agent in other_agents]
        switch_info = (
            f"To switch to another agent, use: change_agent(identifier)\n"
            f"Available: {', '.join(identifiers)}"
        )

        return f"""# Other Agents Available

{roster}

## Agent Switching

{switch_info}

Use agent switching when requested by the user or when it very clearly seems appropriate to do so. 
"""
