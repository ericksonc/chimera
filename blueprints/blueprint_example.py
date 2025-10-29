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

cw_config: CodeWindowWidgetConfig = {
    "base_path": base_path,
    "include": whitelist_code_paths,
    "exclude": blacklist_code_paths,
}

cw_widget = CodeWindowWidget(cw_config)

jarvis.register_widget(cw_widget)

space = GenericSpace(
    jarvis
)  # GenericSpace with no configuration except agent, nothing to serialize except a reference to its own class

raw_blueprint_protocol_json = space.generate_blueprintprotocol_json() # in the near future this will be more of a "save the file to where its supposed to go" type thing

# Now, raw_blueprint_protocol_json can be persisted to disk; new threads can be started with it as base turn 0 configuration.
