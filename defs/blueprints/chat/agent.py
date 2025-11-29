"""Qwen Blueprint - GenericSpace with Qwen agent.

This blueprint creates a single-agent space with the Qwen agent.
"""

from pathlib import Path

from chimera_core.agent import Agent
from chimera_core.spaces.generic_space import GenericSpace

# Compute project root based on current file location
project_root = Path(__file__).parent.parent

# Build absolute paths
agent_yaml_path = project_root / "agents" / "qwen.yaml"
blueprint_json_path = project_root / "blueprints" / "qwen.json"

# Load agent from resolved YAML path
qwen = Agent.from_yaml(str(agent_yaml_path))

# Create space with configured agent
space = GenericSpace(qwen)

# Generate blueprint JSON
if __name__ == "__main__":
    space.serialize_blueprint_json(str(blueprint_json_path))
