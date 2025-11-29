#!/usr/bin/env python3
"""Blueprint: Kimi Engineer - Direct engineering capabilities with EngineeringWidget.

This blueprint creates a Kimi agent with EngineeringWidget for direct file and bash access,
working autonomously in the flex1 worktree.

Usage:
    python blueprints/kimi-engineer.py
"""

from chimera_core.agent import Agent
from chimera_core.spaces.generic_space import GenericSpace
from chimera_core.widgets.engineering_widget import EngineeringWidget

# Load agent from YAML
agent = Agent.from_yaml("agents/kimi-engineer.yaml")

# Add EngineeringWidget (provides file/bash access)
# Note: cwd is NOT set here - it will be resolved dynamically from client context
agent.register_widget(
    EngineeringWidget(
        cwd=None,  # Dynamic CWD
        acceptEdits=True,
        max_file_size=200_000,
    )
)

# Create space
space = GenericSpace(agent)

if __name__ == "__main__":
    # Serialize to JSON
    space.serialize_blueprint_json("blueprints/kimi-engineer.json")
