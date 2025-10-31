"""
Illustrative pseudocode to show how blueprints should be able to be configured in python using object isntances,
objects themselves resolve to BlueprintProtocol
"""

jarvis = Agent.from_yaml(
    "agents/jarvis.yaml"
)  # all fields can be serialized to BlueprintProtocol

base_path = "/Users/ericksonc/appdev/chimera/"  # could also be e.g. a remote path / URL in the future
whitelist_code_paths = [
    "core/protocols/"  # .gitignore style
    "meta/agents/architecture/"
]
blacklist_code_paths = [
    "meta/agents/architecture/archive/"
]  # e.g. exclude paths from included directories

cw_widget = ContextDocsWidget(
    base_path, 
    whitelist_code_paths, 
    exclude=blacklist_code_paths
)

jarvis.register_widget(cw_widget)

space = GenericSpace(
    jarvis
) 