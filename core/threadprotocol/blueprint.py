"""BlueprintProtocol domain objects - Line 1 of ThreadProtocol JSONL.

The blueprint defines Turn 0 configuration: agents, space, widgets.
This module provides domain objects with serialization to/from event format.

Design principles:
- Protocol-first: Event dict is canonical, Python objects are convenience
- Inline for simple/ephemeral, reference for reusable/trackable
- Validation happens at domain object level
- Immutable once written to ThreadProtocol
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Any, TypeVar, Generic
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pathlib import Path

# Type parameter for widget configuration
WidgetConfigT = TypeVar('WidgetConfigT')


# ============================================================================
# Widget Configuration
# ============================================================================

@dataclass
class WidgetConfig(Generic[WidgetConfigT]):
    """Widget configuration - always referenced by class name.

    Generic over the widget's config type (WidgetConfigT).
    Each widget defines its own WidgetBlueprintT type.

    Widgets can appear at two levels:
    - Space-level: Shared across all agents
    - Agent-level: Private to specific agent

    TODO: Add validation using Pydantic AI's approach (Pydantic + dataclasses).
    See how Pydantic AI uses Field() discriminators and validators with dataclasses.
    """
    class_name: str  # e.g., "chimera.widgets.CodeWindowWidget"
    version: str  # e.g., "1.0.0"
    instance_id: str  # UUID for this widget instance
    config: WidgetConfigT  # Typed widget-specific config

    def to_dict(self) -> dict:
        """Convert to event dict format."""
        return {
            "class_name": self.class_name,
            "version": self.version,
            "instance_id": self.instance_id,
            "config": self.config
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WidgetConfig[dict]":
        """Create from event dict format.

        Returns untyped WidgetConfig with dict config.
        Widgets should use their own from_blueprint_config() for typed deserialization.
        """
        return cls(
            class_name=data["class_name"],
            version=data["version"],
            instance_id=data["instance_id"],
            config=data.get("config", {})
        )


# ============================================================================
# Agent Configuration
# ============================================================================

@dataclass
class InlineAgentConfig:
    """Inline agent definition - simple, single-use agents."""
    id: str  # UUID for this agent instance
    name: str  # Human-readable name
    description: str  # How others see this agent
    base_prompt: str  # Core instructions/persona
    model_string: Optional[str] = None  # e.g., "openai:gpt-4o"
    widgets: list[WidgetConfig[Any]] = field(default_factory=list)  # Agent-private widgets

    def to_dict(self) -> dict:
        """Convert to event dict format."""
        result = {
            "type": "inline",
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "base_prompt": self.base_prompt,
            "widgets": [w.to_dict() for w in self.widgets]
        }
        if self.model_string:
            result["model_string"] = self.model_string
        return result

    def validate(self) -> list[str]:
        """Validate configuration.

        TODO: Implement validation using Pydantic AI's approach.
        """
        errors = []
        # Validation to be implemented
        return errors


@dataclass
class ReferencedAgentConfig:
    """Referenced agent - complex, reusable agents."""
    agent_uuid: str  # Canonical UUID from registry
    version: str  # Semantic version to use
    overrides: dict[str, Any] = field(default_factory=dict)  # Field overrides
    widgets: list[WidgetConfig[Any]] = field(default_factory=list)  # Agent-private widgets

    def to_dict(self) -> dict:
        """Convert to event dict format."""
        result = {
            "type": "reference",
            "agent_uuid": self.agent_uuid,
            "version": self.version,
            "widgets": [w.to_dict() for w in self.widgets]
        }
        if self.overrides:
            result["overrides"] = self.overrides
        return result

    def validate(self) -> list[str]:
        """Validate configuration.

        TODO: Implement validation using Pydantic AI's approach.
        """
        errors = []
        # Validation to be implemented
        return errors


# Union type for agents
AgentConfig = InlineAgentConfig | ReferencedAgentConfig


def agent_from_dict(data: dict) -> AgentConfig:
    """Parse agent config from event dict."""
    agent_type = data.get("type")

    if agent_type == "inline":
        return InlineAgentConfig(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            base_prompt=data["base_prompt"],
            model_string=data.get("model_string"),
            widgets=[WidgetConfig.from_dict(w) for w in data.get("widgets", [])]
        )
    elif agent_type == "reference":
        return ReferencedAgentConfig(
            agent_uuid=data["agent_uuid"],
            version=data["version"],
            overrides=data.get("overrides", {}),
            widgets=[WidgetConfig.from_dict(w) for w in data.get("widgets", [])]
        )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


# ============================================================================
# Space Configuration
# ============================================================================

@dataclass
class DefaultSpaceConfig:
    """Default space - GenericSpace with minimal orchestration."""
    widgets: list[WidgetConfig[Any]] = field(default_factory=list)  # Space-shared widgets

    def to_dict(self) -> dict:
        """Convert to event dict format."""
        return {
            "type": "default",
            "widgets": [w.to_dict() for w in self.widgets]
        }

    def validate(self) -> list[str]:
        """Validate configuration.

        TODO: Implement validation using Pydantic AI's approach.
        """
        errors = []
        # Validation to be implemented
        return errors


@dataclass
class ReferencedSpaceConfig:
    """Referenced space - specific Python implementation."""
    class_name: str  # e.g., "chimera.spaces.GroupChatSpace"
    version: str  # e.g., "1.0.0"
    config: dict[str, Any] = field(default_factory=dict)  # Space-specific config
    widgets: list[WidgetConfig[Any]] = field(default_factory=list)  # Space-shared widgets

    def to_dict(self) -> dict:
        """Convert to event dict format."""
        return {
            "type": "reference",
            "class_name": self.class_name,
            "version": self.version,
            "config": self.config,
            "widgets": [w.to_dict() for w in self.widgets]
        }

    def validate(self) -> list[str]:
        """Validate configuration.

        TODO: Implement validation using Pydantic AI's approach.
        """
        errors = []
        # Validation to be implemented
        return errors


# Union type for spaces
SpaceConfig = DefaultSpaceConfig | ReferencedSpaceConfig


def space_from_dict(data: dict) -> SpaceConfig:
    """Parse space config from event dict."""
    space_type = data.get("type", "default")

    if space_type == "default":
        return DefaultSpaceConfig(
            widgets=[WidgetConfig.from_dict(w) for w in data.get("widgets", [])]
        )
    elif space_type == "reference":
        return ReferencedSpaceConfig(
            class_name=data["class_name"],
            version=data["version"],
            config=data.get("config", {}),
            widgets=[WidgetConfig.from_dict(w) for w in data.get("widgets", [])]
        )
    else:
        raise ValueError(f"Unknown space type: {space_type}")


# ============================================================================
# Blueprint - Line 1 of ThreadProtocol
# ============================================================================

@dataclass
class Blueprint:
    """Blueprint configuration - always Line 1 of ThreadProtocol JSONL.

    Defines Turn 0 state: what agents exist, what space they're in,
    what widgets are available.

    This is immutable once written. Changes require:
    - Creating a new thread with new blueprint, OR
    - Using state mutations within existing constraints
    """
    thread_id: str  # UUID of the thread
    space: SpaceConfig  # Space configuration
    agents: list[AgentConfig]  # Agent configurations
    blueprint_version: str = "0.0.1"  # Protocol version
    max_turns: Optional[int] = None  # Optional turn limit
    max_depth: Optional[int] = None  # Optional depth limit

    def to_event(self) -> dict:
        """Serialize to thread_blueprint event (Line 1 of JSONL).

        Returns:
            Event dict ready to write as first line
        """
        blueprint_data = {
            "space": self.space.to_dict(),
            "agents": [a.to_dict() for a in self.agents]
        }

        # Add optional guardrails
        if self.max_turns is not None:
            blueprint_data["max_turns"] = self.max_turns
        if self.max_depth is not None:
            blueprint_data["max_depth"] = self.max_depth

        return {
            "event_type": "thread_blueprint",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thread_id": self.thread_id,
            "blueprint_version": self.blueprint_version,
            "blueprint": blueprint_data
        }

    @classmethod
    def from_event(cls, event: dict) -> "Blueprint":
        """Parse from thread_blueprint event.

        Args:
            event: Blueprint event dict (Line 1 of JSONL)

        Returns:
            Blueprint instance

        Raises:
            ValueError: If event is invalid
        """
        if event.get("event_type") != "thread_blueprint":
            raise ValueError(f"Not a blueprint event: {event.get('event_type')}")

        blueprint_data = event["blueprint"]

        return cls(
            thread_id=event["thread_id"],
            blueprint_version=event.get("blueprint_version", "0.0.1"),
            space=space_from_dict(blueprint_data.get("space", {"type": "default"})),
            agents=[agent_from_dict(a) for a in blueprint_data["agents"]],
            max_turns=blueprint_data.get("max_turns"),
            max_depth=blueprint_data.get("max_depth")
        )

    def validate(self) -> list[str]:
        """Validate the blueprint configuration.

        TODO: Implement validation using Pydantic AI's approach.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        # Validation to be implemented
        return errors

    def get_widgets_for_agent(self, agent_id: str) -> list[WidgetConfig[Any]]:
        """Get all widgets available to a specific agent.

        This includes:
        - Space-level widgets (shared)
        - Agent-level widgets (private)

        Args:
            agent_id: UUID of the agent

        Returns:
            List of widget configs available to this agent
        """
        widgets = []

        # Add space-level widgets
        widgets.extend(self.space.widgets)

        # Find and add agent-level widgets
        for agent in self.agents:
            if isinstance(agent, InlineAgentConfig) and agent.id == agent_id:
                widgets.extend(agent.widgets)
                break
            # Note: Referenced agents would need registry lookup for ID

        return widgets


# ============================================================================
# Convenience Functions
# ============================================================================

def create_simple_blueprint(
    agent_name: str = "Assistant",
    agent_prompt: str = "You are a helpful assistant.",
    model_string: str = "openai:gpt-4o-mini",
    thread_id: Optional[str] = None
) -> Blueprint:
    """Create a minimal blueprint for single-agent conversation.

    This is the simplest case: one inline agent with GenericSpace.

    Args:
        agent_name: Name of the agent
        agent_prompt: System prompt for the agent
        model_string: Model to use
        thread_id: Optional thread ID (generated if not provided)

    Returns:
        Blueprint instance
    """
    if not thread_id:
        thread_id = str(uuid4())

    agent = InlineAgentConfig(
        id=str(uuid4()),
        name=agent_name,
        description=f"A helpful {agent_name.lower()}",
        base_prompt=agent_prompt,
        model_string=model_string
    )

    space = DefaultSpaceConfig()

    return Blueprint(
        thread_id=thread_id,
        space=space,
        agents=[agent]
    )


def load_agent_from_registry(agent_name: str, version: str = "latest") -> dict:
    """Load agent definition from registry (YAML files).

    Args:
        agent_name: Name of the agent (maps to filename)
        version: Version to load (or "latest")

    Returns:
        Agent definition dict

    Raises:
        FileNotFoundError: If agent file doesn't exist
        ValueError: If version not found
    """
    # TODO: Implement when agent registry is set up
    # For now, this is a placeholder showing the interface
    agents_dir = Path("agents")
    agent_file = agents_dir / f"{agent_name}.yaml"

    if not agent_file.exists():
        raise FileNotFoundError(f"Agent not found: {agent_name}")

    # Would load YAML and return the definition
    # Including the UUID that's inside the file
    raise NotImplementedError("Agent registry not yet implemented")