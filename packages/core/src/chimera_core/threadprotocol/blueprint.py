"""BlueprintProtocol domain objects - Line 1 of ThreadProtocol JSONL.

The blueprint defines Turn 0 configuration: agents, space, widgets.
This module provides domain objects with serialization to/from event format.

Design principles:
- Protocol-first: Event dict is canonical, Python objects are convenience
- Inline for simple/ephemeral, reference for reusable/trackable
- Validation happens at domain object level
- Immutable once written to ThreadProtocol
- v0.0.7: Uses camelCase for all fields (matches VSP v6 format)
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ThreadProtocol format version (separate from blueprint schema version)
THREAD_PROTOCOL_VERSION = "0.0.7"

# Type parameter for component configuration
ComponentConfigT = TypeVar("ComponentConfigT")


# ============================================================================
# Component Configuration (Widgets, Cells, etc.)
# ============================================================================


class ComponentConfig(BaseModel, Generic[ComponentConfigT]):
    """Component configuration - always referenced by class name.

    Generic over the component's config type (ComponentConfigT).
    Each component (Widget, Cell, etc.) defines its own BlueprintT type.

    Components can appear at two levels:
    - Space-level: Shared across all agents
    - Agent-level: Private to specific agent
    """

    model_config = ConfigDict(populate_by_name=True)

    class_name: str = Field(alias="className")  # e.g., "chimera.widgets.CodeWindowWidget"
    version: str  # e.g., "1.0.0"
    instance_id: str = Field(alias="instanceId")  # UUID for this component instance
    config: ComponentConfigT  # Typed component-specific config

    def to_dict(self) -> dict:
        """Convert to event dict format (camelCase)."""
        return {
            "className": self.class_name,
            "version": self.version,
            "instanceId": self.instance_id,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentConfig[dict]":
        """Create from event dict format (camelCase).

        Returns untyped ComponentConfig with dict config.
        Components should use their own from_blueprint_config() for typed deserialization.
        """
        return cls(
            class_name=data["className"],
            version=data["version"],
            instance_id=data["instanceId"],
            config=data.get("config", {}),
        )


# ============================================================================
# Agent Configuration
# ============================================================================


class InlineAgentConfig(BaseModel):
    """Inline agent definition - simple, single-use agents.

    v0.0.7 changes:
    - id is now a string identifier (not UUID) - alphanumeric + "-" + "_" only
    - id must be unique within the thread
    - global_uuid is optional (for future universal agent registry)
    - identifier field removed (redundant with id)
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str  # String identifier (alphanumeric + "-" + "_"), unique within thread
    name: str  # Human-readable name
    description: str  # How others see this agent
    base_prompt: str = Field(alias="basePrompt")  # Core instructions/persona
    global_uuid: Optional[str] = Field(
        None, alias="globalUuid"
    )  # Optional UUID for global registry
    model_string: Optional[str] = Field(None, alias="modelString")  # e.g., "openai:gpt-4o"
    widgets: list[ComponentConfig[Any]] = Field(default_factory=list)  # Agent-private widgets
    metadata: dict[str, Any] = Field(default_factory=dict)  # Extra fields (voice_id, etc.)

    @field_validator("id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent ID format: alphanumeric + "-" + "_" only."""
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                f"Agent ID '{v}' must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v

    def to_dict(self) -> dict:
        """Convert to event dict format (camelCase)."""
        result = {
            "type": "inline",
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "basePrompt": self.base_prompt,
            "widgets": [w.to_dict() for w in self.widgets],
        }
        if self.global_uuid:
            result["globalUuid"] = self.global_uuid
        if self.model_string:
            result["modelString"] = self.model_string
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class ReferencedAgentConfig(BaseModel):
    """Referenced agent - complex, reusable agents."""

    model_config = ConfigDict(populate_by_name=True)

    agent_uuid: str = Field(alias="agentUuid")  # Canonical UUID from registry
    version: str  # Semantic version to use
    overrides: dict[str, Any] = Field(default_factory=dict)  # Field overrides
    widgets: list[ComponentConfig[Any]] = Field(default_factory=list)  # Agent-private widgets

    def to_dict(self) -> dict:
        """Convert to event dict format (camelCase)."""
        result = {
            "type": "reference",
            "agentUuid": self.agent_uuid,
            "version": self.version,
            "widgets": [w.to_dict() for w in self.widgets],
        }
        if self.overrides:
            result["overrides"] = self.overrides
        return result


# Union type for agents
AgentConfig = InlineAgentConfig | ReferencedAgentConfig


def agent_from_dict(data: dict) -> AgentConfig:
    """Parse agent config from event dict (camelCase)."""
    agent_type = data.get("type")

    if agent_type == "inline":
        return InlineAgentConfig(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            base_prompt=data["basePrompt"],
            global_uuid=data.get("globalUuid"),
            model_string=data.get("modelString"),
            widgets=[ComponentConfig.from_dict(w) for w in data.get("widgets", [])],
            metadata=data.get("metadata", {}),
        )
    elif agent_type == "reference":
        return ReferencedAgentConfig(
            agent_uuid=data["agentUuid"],
            version=data["version"],
            overrides=data.get("overrides", {}),
            widgets=[ComponentConfig.from_dict(w) for w in data.get("widgets", [])],
        )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


# ============================================================================
# Space Configuration
# ============================================================================


class DefaultSpaceConfig(BaseModel):
    """Default space - GenericSpace with minimal orchestration."""

    model_config = ConfigDict(populate_by_name=True)

    agents: list[AgentConfig] = Field(default_factory=list)  # Agents in this space
    widgets: list[ComponentConfig[Any]] = Field(default_factory=list)  # Space-shared widgets

    def to_dict(self) -> dict:
        """Convert to event dict format (camelCase)."""
        return {
            "type": "default",
            "agents": [a.to_dict() for a in self.agents],
            "widgets": [w.to_dict() for w in self.widgets],
        }


class ReferencedSpaceConfig(BaseModel):
    """Referenced space - specific Python implementation."""

    model_config = ConfigDict(populate_by_name=True)

    class_name: str = Field(alias="className")  # e.g., "chimera.spaces.GroupChatSpace"
    version: str  # e.g., "1.0.0"
    agents: list[AgentConfig] = Field(default_factory=list)  # Agents in this space
    config: dict[str, Any] = Field(default_factory=dict)  # Space-specific config
    widgets: list[ComponentConfig[Any]] = Field(default_factory=list)  # Space-shared widgets

    def to_dict(self) -> dict:
        """Convert to event dict format (camelCase)."""
        return {
            "type": "reference",
            "className": self.class_name,
            "version": self.version,
            "agents": [a.to_dict() for a in self.agents],
            "config": self.config,
            "widgets": [w.to_dict() for w in self.widgets],
        }


# Union type for spaces
SpaceConfig = DefaultSpaceConfig | ReferencedSpaceConfig


def space_from_dict(data: dict) -> SpaceConfig:
    """Parse space config from event dict (camelCase)."""
    space_type = data.get("type", "default")

    if space_type == "default":
        return DefaultSpaceConfig(
            agents=[agent_from_dict(a) for a in data.get("agents", [])],
            widgets=[ComponentConfig.from_dict(w) for w in data.get("widgets", [])],
        )
    elif space_type == "reference":
        return ReferencedSpaceConfig(
            class_name=data["className"],
            version=data["version"],
            agents=[agent_from_dict(a) for a in data.get("agents", [])],
            config=data.get("config", {}),
            widgets=[ComponentConfig.from_dict(w) for w in data.get("widgets", [])],
        )
    else:
        raise ValueError(f"Unknown space type: {space_type}")


# ============================================================================
# Blueprint - Line 1 of ThreadProtocol
# ============================================================================


class Blueprint(BaseModel):
    """Blueprint configuration - always Line 1 of ThreadProtocol JSONL.

    Defines Turn 0 state: what space exists (which contains agents),
    what widgets are available.

    This is immutable once written. Changes require:
    - Creating a new thread with new blueprint, OR
    - Using state mutations within existing constraints
    """

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")  # UUID of the thread
    space: SpaceConfig  # Space configuration (contains agents)
    blueprint_version: str = Field("0.0.7", alias="blueprintVersion")  # Protocol version (v0.0.7)
    max_turns: Optional[int] = Field(None, alias="maxTurns")  # Optional turn limit
    max_depth: Optional[int] = Field(None, alias="maxDepth")  # Optional depth limit

    @field_validator("space")
    @classmethod
    def validate_unique_agent_ids(cls, v: SpaceConfig) -> SpaceConfig:
        """Ensure all agent IDs are unique within the space."""
        agent_ids = []
        for agent in v.agents:
            if isinstance(agent, InlineAgentConfig):
                agent_ids.append(agent.id)
            # Note: ReferencedAgentConfig would need registry lookup for ID validation

        duplicates = [aid for aid in agent_ids if agent_ids.count(aid) > 1]
        if duplicates:
            raise ValueError(f"Duplicate agent IDs found: {set(duplicates)}")

        return v

    def to_event(self) -> dict:
        """Serialize to thread-blueprint event (Line 1 of JSONL).

        Returns:
            Event dict ready to write as first line (camelCase, hyphenated type)
        """
        blueprint_data = {"space": self.space.to_dict()}

        # Add optional guardrails
        if self.max_turns is not None:
            blueprint_data["maxTurns"] = self.max_turns
        if self.max_depth is not None:
            blueprint_data["maxDepth"] = self.max_depth

        return {
            "type": "thread-blueprint",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "threadId": self.thread_id,
            "threadProtocolVersion": THREAD_PROTOCOL_VERSION,  # Format version
            "blueprintVersion": self.blueprint_version,  # Schema version
            "blueprint": blueprint_data,
        }

    @classmethod
    def from_event(cls, event: dict) -> "Blueprint":
        """Parse from thread-blueprint event (camelCase).

        Args:
            event: Blueprint event dict (Line 1 of JSONL)

        Returns:
            Blueprint instance

        Raises:
            ValueError: If event is invalid or version mismatch
        """
        if event.get("type") != "thread-blueprint":
            raise ValueError(f"Not a blueprint event: {event.get('type')}")

        # Validate ThreadProtocol format version
        thread_protocol_version = event.get(
            "threadProtocolVersion", "0.0.1"
        )  # Default for old files
        if thread_protocol_version != THREAD_PROTOCOL_VERSION:
            raise ValueError(
                f"ThreadProtocol version mismatch: expected {THREAD_PROTOCOL_VERSION}, "
                f"got {thread_protocol_version}. This thread may require migration or was "
                f"created with an incompatible version of Chimera."
            )

        blueprint_data = event["blueprint"]

        return cls(
            thread_id=event["threadId"],
            blueprint_version=event.get("blueprintVersion", "0.0.7"),
            space=space_from_dict(blueprint_data.get("space", {"type": "default"})),
            max_turns=blueprint_data.get("maxTurns"),
            max_depth=blueprint_data.get("maxDepth"),
        )

    def get_widgets_for_agent(self, agent_id: str) -> list[ComponentConfig[Any]]:
        """Get all widgets available to a specific agent.

        This includes:
        - Space-level widgets (shared)
        - Agent-level widgets (private)

        Args:
            agent_id: UUID of the agent

        Returns:
            List of component configs available to this agent
        """
        widgets = []

        # Add space-level widgets
        widgets.extend(self.space.widgets)

        # Find and add agent-level widgets from agents nested under space
        for agent in self.space.agents:
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
    thread_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Blueprint:
    """Create a minimal blueprint for single-agent conversation.

    This is the simplest case: one inline agent with GenericSpace.

    Args:
        agent_name: Name of the agent
        agent_prompt: System prompt for the agent
        model_string: Model to use
        thread_id: Optional thread ID (generated if not provided)
        agent_id: Optional agent identifier (generated from name if not provided)

    Returns:
        Blueprint instance
    """
    if not thread_id:
        thread_id = str(uuid4())

    if not agent_id:
        # Generate identifier from name: lowercase, replace spaces with hyphens
        agent_id = re.sub(r"[^a-zA-Z0-9-]", "-", agent_name.lower())
        agent_id = re.sub(r"-+", "-", agent_id).strip("-")  # Clean up multiple hyphens

    agent = InlineAgentConfig(
        id=agent_id,
        name=agent_name,
        description=f"A helpful {agent_name.lower()}",
        base_prompt=agent_prompt,  # Use field name (Pydantic handles alias)
        model_string=model_string,
    )

    space = DefaultSpaceConfig(agents=[agent])

    return Blueprint(
        thread_id=thread_id,  # Use field name (Pydantic handles alias)
        space=space,
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
