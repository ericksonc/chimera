"""Base classes and stub implementations for core Chimera types.

These are the concrete classes that implement our protocols.
For MVP, these are minimal stubs that will be fleshed out as we build.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from core.protocols.readable_thread_state import ReadableThreadState


# ============================================================================
# Widget Base Classes
# ============================================================================

@dataclass
class Widget:
    """Base class for all widgets.

    Widgets can be attached at:
    - Space level: Shared across all agents
    - Agent level: Private to specific agent
    """
    instance_id: str
    config: dict = field(default_factory=dict)

    def get_ambient_context(self, state: 'ReadableThreadState') -> str | None:
        """Generate ambient context for this widget.

        Returns None if no context to add this turn.
        """
        return None

    def register_mutation(self, mutation: dict, agent_id: UUID | None = None):
        """Register a state mutation (will be implemented later)."""
        pass


# ============================================================================
# Space Base Classes
# ============================================================================

@dataclass
class Space:
    """Base class for all spaces.

    A space is an execution environment for agents.
    """
    space_class: str = "chimera.spaces.Space"
    space_version: str = "1.0.0"
    config: dict = field(default_factory=dict)
    widgets: dict[str, Widget] = field(default_factory=dict)

    async def run_turn(self, user_message: str, state: 'ReadableThreadState') -> dict:
        """Execute a turn in this space.

        Returns:
            Dict with response data (text, tool calls, etc.)
        """
        raise NotImplementedError


class GenericSpace(Space):
    """Simplest possible space - single agent wrapper.

    This is our MVP space that just runs one agent with Pydantic AI.
    No orchestration, no multi-agent logic - just a direct wrapper.
    """
    space_class: str = "chimera.spaces.GenericSpace"

    def __init__(self, agent: 'Agent', config: dict | None = None):
        super().__init__(
            space_class="chimera.spaces.GenericSpace",
            space_version="1.0.0",
            config=config or {},
            widgets={}
        )
        self.agent = agent
        # self._pydantic_agent = None  # Will be initialized later

    # def initialize_pydantic_agent(self):
    #     """Initialize the Pydantic AI agent.

    #     This is called after the space is created to set up the actual AI agent.
    #     """
    #     from pydantic_ai import Agent as PydanticAgent

    #     # Create Pydantic AI agent with the configured model
    #     self._pydantic_agent = PydanticAgent(
    #         model=self.agent.model_string or "openai:gpt-4o-mini",
    #         system_prompt=self.agent.base_prompt
    #     )

    # async def run_turn(
    #     self,
    #     user_message: str,
    #     history: list,  # ModelMessage list
    #     state: 'ReadableThreadState'
    # ) -> dict:
    #     """Run a single agent turn.

    #     Args:
    #         user_message: The user's message
    #         history: Previous conversation history as ModelMessages
    #         state: Current thread state

    #     Returns:
    #         Dict with response parts and usage info
    #     """
    #     if self._pydantic_agent is None:
    #         self.initialize_pydantic_agent()

    #     # Run the agent with history
    #     # For MVP, we'll use the synchronous run method
    #     # In future, we'll use streaming
    #     result = await self._pydantic_agent.run(
    #         user_message,
    #         message_history=history
    #     )

    #     # Extract response parts and usage
    #     return {
    #         "text": result.data if isinstance(result.data, str) else str(result.data),
    #         "usage": {
    #             "input_tokens": result.usage().request_tokens if result.usage() else 0,
    #             "output_tokens": result.usage().response_tokens if result.usage() else 0,
    #             "total_tokens": result.usage().total_tokens if result.usage() else 0
    #         },
    #         "model_name": result.model if hasattr(result, 'model') else None
    #     }


# ============================================================================
# Agent Base Classes
# ============================================================================

@dataclass
class Agent:
    """Base class for all agents."""
    agent_id: UUID
    name: str
    description: str
    base_prompt: str
    model_string: str | None = None
    widgets: dict[str, Widget] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.agent_id),
            "name": self.name,
            "description": self.description,
            "base_prompt": self.base_prompt,
            "model_string": self.model_string,
        }


# ============================================================================
# Blueprint Types
# ============================================================================

@dataclass
class Blueprint:
    """Parsed blueprint from Line 1 of JSONL."""
    thread_id: UUID
    timestamp: datetime
    blueprint_version: str
    space_config: dict
    agents: list[dict]
    tools: list[dict] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)

    @classmethod
    def from_event(cls, event: dict) -> 'Blueprint':
        """Parse from blueprint event."""
        bp = event["blueprint"]
        return cls(
            thread_id=UUID(event["thread_id"]),
            timestamp=datetime.fromisoformat(event["timestamp"]),
            blueprint_version=event["blueprint_version"],
            space_config=bp.get("space", {}),
            agents=bp.get("agents", []),
            tools=bp.get("tools", []),
            mcp_servers=bp.get("mcp_servers", [])
        )


# ============================================================================
# Thread State Implementation
# ============================================================================

@dataclass
class ThreadState:
    """Concrete implementation of ReadableThreadState protocol.

    This is the actual state object that gets passed around during execution.
    Implements all properties required by ReadableThreadState.
    """
    # Core identity
    thread_id: UUID
    parent_thread_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Blueprint (will be set from Line 1 of JSONL)
    _blueprint: Blueprint | None = None

    # Active state (set during execution)
    _space: Space | None = None
    _active_agent: Agent | None = None

    # Progress tracking
    turn_number: int = 0

    # Token usage (updated from Pydantic AI responses)
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    # Guardrails (from blueprint)
    max_turns: int | None = None
    max_depth: int | None = None

    # ReadableThreadState protocol properties

    @property
    def space(self) -> Space:
        """Active space."""
        if self._space is None:
            raise RuntimeError("Space not initialized")
        return self._space

    @property
    def active_agent(self) -> Agent:
        """Currently active agent."""
        if self._active_agent is None:
            raise RuntimeError("No active agent")
        return self._active_agent

    @property
    def blueprint(self) -> Blueprint:
        """Blueprint view."""
        if self._blueprint is None:
            raise RuntimeError("Blueprint not loaded")
        return self._blueprint

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens

    @property
    def depth(self) -> int:
        """Calculate thread depth."""
        if self.parent_thread_id is None:
            return 0
        # In real implementation, would look up parent chain
        # For MVP, we don't support thread spawning yet
        return 1

    def update_usage(self, usage: dict):
        """Update token usage from Pydantic AI response."""
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.reasoning_tokens += usage.get("reasoning_tokens", 0)

    def set_blueprint(self, blueprint: Blueprint):
        """Set blueprint and initialize guardrails."""
        self._blueprint = blueprint
        self.thread_id = blueprint.thread_id
        self.created_at = blueprint.timestamp
        # Extract guardrails if present
        bp_data = blueprint.space_config
        self.max_turns = bp_data.get("max_turns")
        self.max_depth = bp_data.get("max_depth")

    def set_space(self, space: Space):
        """Set active space."""
        self._space = space

    def set_active_agent(self, agent: Agent):
        """Set active agent."""
        self._active_agent = agent


# ============================================================================
# Re-export for convenience
# ============================================================================

__all__ = [
    'Widget',
    'Space',
    'GenericSpace',
    'Agent',
    'Blueprint',
    'ThreadState',
]