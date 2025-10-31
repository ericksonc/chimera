"""First Blueprint - Jarvis with ContextDocs widget.

This blueprint creates a single-agent space with Jarvis and a ContextDocsWidget
that provides project documentation as ambient context.
"""

import sys
sys.path.insert(0, '/Users/ericksonc/appdev/chimera')

from core.agent import Agent
from core.spaces.generic_space import GenericSpace
from core.widgets import ContextDocsWidget

# Load Jarvis agent from YAML registry
jarvis = Agent.from_yaml("agents/jarvis.yaml")

# Create ContextDocsWidget with project documentation
base_path = "/Users/ericksonc/appdev/chimera/"
whitelist_paths = [
    "core/protocols/",
    "meta/agents/architecture/"
]
blacklist_paths = [
    "meta/agents/architecture/archive/"
]

context_widget = ContextDocsWidget(
    base_path=base_path,
    whitelist_paths=whitelist_paths,
    blacklist_paths=blacklist_paths
)

# Register widget to agent
jarvis.register_widget(context_widget)

# Create space with configured agent
space = GenericSpace(jarvis)

# Generate blueprint JSON
if __name__ == "__main__":
    space.serialize_blueprint_json("blueprints/first_blueprint.json") 