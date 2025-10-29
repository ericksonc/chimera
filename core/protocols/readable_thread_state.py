"""ReadableThreadState Protocol - Read-only thread state interface.

This protocol defines the interface passed to lifecycle hooks, agents, widgets,
and spaces during thread execution. It provides access to current state without
allowing direct mutations.

Key principle: "What's available wherever you are"
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable, TYPE_CHECKING
from uuid import UUID
from datetime import datetime

if TYPE_CHECKING:
    from core.base import Widget


@runtime_checkable
class ActiveSpace(Protocol):
    """Minimal execution interface between thread.py and Space implementations.

    This is what thread.py needs to run the space. Space implementations
    are responsible for:
    - Determining the active agent
    - Composing the agent's POV (message history, tools, context)
    - Running the agent
    - Returning results

    thread.py doesn't know HOW - it just calls run_stream().
    """

    @property
    def active_agent(self) -> ActiveAgent:
        """The currently active agent (for recording who produced output)."""
        ...

    async def run_stream(self, state: ReadableThreadState) -> Any:
        """Run the active agent and return result.

        Args:
            state: Read-only view of current thread state

        Returns:
            AgentRunResult from Pydantic AI

        This method:
        1. Determines which agent should run (in multi-agent, may rotate)
        2. Composes agent's POV (message transformer, tools, ambient context)
        3. Runs agent.iter() or equivalent
        4. Returns result for thread.py to record in ThreadProtocol
        """
        ...


@runtime_checkable
class ActiveAgent(Protocol):
    """Read-only view of the active agent."""

    @property
    def agent_id(self) -> UUID:
        """Agent's UUID."""
        ...

    @property
    def name(self) -> str:
        """Agent's name."""
        ...

    @property
    def description(self) -> str:
        """How this agent is seen by others."""
        ...

    @property
    def model_string(self) -> str | None:
        """Model string if specified (e.g., 'openai:gpt-4o')."""
        ...

    @property
    def widgets(self) -> dict[str, Widget]:
        """Agent-level widgets (private to this agent)."""
        ...


@runtime_checkable
class BlueprintView(Protocol):
    """Read-only view of BlueprintProtocol."""

    @property
    def agents(self) -> list[dict]:
        """All agent definitions from blueprint."""
        ...

    @property
    def tools(self) -> list[dict]:
        """Tool configurations from blueprint."""
        ...

    @property
    def mcp_servers(self) -> list[dict]:
        """MCP server configurations from blueprint."""
        ...


@runtime_checkable
class ReadableThreadState(Protocol):
    """Read-only view of thread state during execution.

    This is what gets passed to:
    - Lifecycle hooks
    - Agent execution
    - Widget ambient context generation
    - Space orchestration logic
    """

    # ===== Main Primitives =====

    @property
    def active_agent(self) -> ActiveAgent:
        """The currently active agent.

        ActiveAgent exposes:
        - agent_id: UUID
        - name: str
        - description: str
        - model_string: str (if specified)
        - widgets: dict[str, Widget] (agent-level widgets)
        """
        ...

    @property
    def blueprint(self) -> BlueprintView:
        """Read-only view of the BlueprintProtocol (Turn 0 configuration).

        BlueprintView exposes:
        - agents: list[dict] (all agent definitions)
        - tools: list[dict] (tool configurations)
        - mcp_servers: list[dict] (MCP configurations)

        This is the blueprint field from Line 1 of the JSONL.
        """
        ...

    # ===== Thread Details =====

    @property
    def turn_number(self) -> int:
        """Current turn number (0-based).

        Calculated field based on elapsed turns.
        Turn 0 = blueprint only (no conversation yet)
        Turn 1 = after first user message + agent response
        etc.
        """
        ...

    @property
    def thread_id(self) -> UUID:
        """UUID of this thread."""
        ...

    @property
    def parent_thread_id(self) -> UUID | None:
        """UUID of the thread that spawned this thread.

        None if this is a root thread.
        """
        ...

    @property
    def depth(self) -> int:
        """Thread depth from root (0-based).

        - 0 = root thread (parent_thread_id is None)
        - 1 = spawned by root thread
        - 2 = spawned by depth-1 thread
        - etc.
        """
        ...

    # ===== Usage Details =====
    # Note: These are aggregated from Pydantic AI ModelResponse objects

    @property
    def input_tokens(self) -> int:
        """Total input tokens used in this thread so far."""
        ...

    @property
    def output_tokens(self) -> int:
        """Total output tokens used in this thread so far.

        Includes reasoning tokens.
        """
        ...

    @property
    def reasoning_tokens(self) -> int:
        """Total reasoning tokens used in this thread so far.

        This is a subset of output_tokens.
        """
        ...

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output) used in this thread so far."""
        ...

    # ===== Metadata =====

    @property
    def created_at(self) -> datetime:
        """When this thread was created (UTC).

        From BlueprintProtocol timestamp (Line 1 of JSONL).
        """
        ...

    # ===== Guardrails (Optional) =====

    @property
    def max_turns(self) -> int | None:
        """Maximum number of AgentTurns allowed in this thread.

        None = no limit.
        """
        ...

    @property
    def max_depth(self) -> int | None:
        """Maximum thread spawning depth allowed (0-based).

        - 0 = no spawning allowed
        - 1 = can spawn threads, but those can't spawn
        - 2 = can spawn threads that can spawn threads
        - None = no limit
        """
        ...
