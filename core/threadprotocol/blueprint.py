"""BlueprintProtocol handling - Create and parse blueprint events.

The blueprint is always Line 1 of a ThreadProtocol JSONL file.
It defines the Turn 0 configuration: agents, space, tools, etc.
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, Any


def create_blueprint_event(
    thread_id: str | UUID | None = None,
    space: dict | None = None,
    agents: list[dict] | None = None,
    tools: list[dict] | None = None,
    mcp_servers: list[dict] | None = None,
    max_turns: int | None = None,
    max_depth: int | None = None,
    blueprint_version: str = "0.0.1"
) -> dict:
    """Create a blueprint event for Line 1 of ThreadProtocol JSONL.

    Args:
        thread_id: UUID for the thread (generated if not provided)
        space: Space configuration (defaults to GenericSpace)
        agents: List of agent definitions
        tools: List of tool configurations
        mcp_servers: List of MCP server configurations
        max_turns: Optional maximum turns allowed
        max_depth: Optional maximum thread depth allowed
        blueprint_version: Version of blueprint protocol

    Returns:
        Blueprint event dictionary ready to write as Line 1
    """
    if thread_id is None:
        thread_id = str(uuid4())
    elif isinstance(thread_id, UUID):
        thread_id = str(thread_id)

    # Default to GenericSpace if no space specified
    if space is None:
        space = {"type": "default"}

    # Must have at least one agent
    if not agents:
        raise ValueError("At least one agent must be defined in blueprint")

    blueprint = {
        "space": space,
        "agents": agents,
        "tools": tools or [],
        "mcp_servers": mcp_servers or []
    }

    # Add optional guardrails if specified
    if max_turns is not None:
        blueprint["max_turns"] = max_turns
    if max_depth is not None:
        blueprint["max_depth"] = max_depth

    return {
        "event_type": "thread_blueprint",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "thread_id": thread_id,
        "blueprint_version": blueprint_version,
        "blueprint": blueprint
    }


def create_simple_blueprint(
    agent_name: str = "Assistant",
    agent_prompt: str = "You are a helpful assistant.",
    model_string: str = "openai:gpt-4o-mini",
    thread_id: str | UUID | None = None
) -> dict:
    """Create a minimal blueprint for single-agent conversation.

    This is a convenience function for the most common case:
    a single agent with GenericSpace.

    Args:
        agent_name: Name of the agent
        agent_prompt: System prompt for the agent
        model_string: Model to use (e.g., "openai:gpt-4o")
        thread_id: Optional thread ID

    Returns:
        Blueprint event dictionary
    """
    agent = {
        "type": "inline",
        "id": str(uuid4()),
        "name": agent_name,
        "description": f"A helpful {agent_name.lower()}",
        "base_prompt": agent_prompt,
        "model_string": model_string
    }

    return create_blueprint_event(
        thread_id=thread_id,
        agents=[agent],
        space={"type": "default"}
    )


def parse_blueprint_event(event: dict) -> dict:
    """Parse and validate a blueprint event.

    Args:
        event: Blueprint event dictionary

    Returns:
        Parsed blueprint data

    Raises:
        ValueError: If event is not a valid blueprint
    """
    if event.get("event_type") != "thread_blueprint":
        raise ValueError(f"Not a blueprint event: {event.get('event_type')}")

    required_fields = ["thread_id", "blueprint_version", "blueprint"]
    for field in required_fields:
        if field not in event:
            raise ValueError(f"Blueprint missing required field: {field}")

    blueprint = event["blueprint"]
    if "agents" not in blueprint or not blueprint["agents"]:
        raise ValueError("Blueprint must define at least one agent")

    return {
        "thread_id": event["thread_id"],
        "blueprint_version": event["blueprint_version"],
        "timestamp": event.get("timestamp"),
        "space": blueprint.get("space", {"type": "default"}),
        "agents": blueprint["agents"],
        "tools": blueprint.get("tools", []),
        "mcp_servers": blueprint.get("mcp_servers", []),
        "max_turns": blueprint.get("max_turns"),
        "max_depth": blueprint.get("max_depth")
    }


def extract_agent_configs(blueprint: dict) -> list[dict]:
    """Extract agent configurations from a blueprint.

    Args:
        blueprint: Blueprint data (from parse_blueprint_event)

    Returns:
        List of agent configuration dictionaries
    """
    agents = []
    for agent_def in blueprint.get("agents", []):
        if agent_def.get("type") == "inline":
            # Inline agent definition
            agents.append({
                "id": agent_def["id"],
                "name": agent_def["name"],
                "description": agent_def.get("description", ""),
                "base_prompt": agent_def["base_prompt"],
                "model_string": agent_def.get("model_string"),
                "tools": agent_def.get("tools", []),
                "widgets": agent_def.get("widgets", [])
            })
        elif agent_def.get("type") == "reference":
            # Referenced agent (would load from registry in real implementation)
            # For MVP, we'll skip this
            raise NotImplementedError("Referenced agents not yet supported")
        else:
            raise ValueError(f"Unknown agent type: {agent_def.get('type')}")

    return agents


def extract_space_config(blueprint: dict) -> dict:
    """Extract space configuration from a blueprint.

    Args:
        blueprint: Blueprint data (from parse_blueprint_event)

    Returns:
        Space configuration dictionary
    """
    space = blueprint.get("space", {"type": "default"})

    if space.get("type") == "default":
        # GenericSpace - single agent wrapper
        return {
            "class": "chimera.spaces.GenericSpace",
            "version": "1.0.0",
            "config": {},
            "widgets": space.get("widgets", [])
        }
    elif space.get("type") == "reference":
        # Specific space class
        return {
            "class": space["class_name"],
            "version": space["version"],
            "config": space.get("config", {}),
            "widgets": space.get("widgets", [])
        }
    else:
        raise ValueError(f"Unknown space type: {space.get('type')}")