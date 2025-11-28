"""Tests for BlueprintProtocol domain objects."""

from uuid import uuid4

import pytest

from chimera_core.threadprotocol.blueprint import (
    Blueprint,
    ComponentConfig,
    DefaultSpaceConfig,
    InlineAgentConfig,
    ReferencedAgentConfig,
    ReferencedSpaceConfig,
    agent_from_dict,
    create_simple_blueprint,
)


class TestComponentConfig:
    """Tests for ComponentConfig."""

    def test_create_widget_config(self):
        """Test creating a widget config."""
        widget = ComponentConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001",
            config={"paths": ["src/**/*.py"]},
        )

        assert widget.class_name == "chimera.widgets.CodeWindowWidget"
        assert widget.version == "1.0.0"
        assert widget.instance_id == "widget-001"
        assert widget.config == {"paths": ["src/**/*.py"]}

    def test_widget_to_dict(self):
        """Test widget serialization."""
        widget = ComponentConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001",
            config={"paths": ["src/**/*.py"]},
        )

        result = widget.to_dict()

        assert result == {
            "className": "chimera.widgets.CodeWindowWidget",
            "version": "1.0.0",
            "instanceId": "widget-001",
            "config": {"paths": ["src/**/*.py"]},
        }

    def test_widget_from_dict(self):
        """Test widget deserialization."""
        data = {
            "className": "chimera.widgets.CodeWindowWidget",
            "version": "1.0.0",
            "instanceId": "widget-001",
            "config": {"paths": ["src/**/*.py"]},
        }

        widget = ComponentConfig.from_dict(data)

        assert widget.class_name == "chimera.widgets.CodeWindowWidget"
        assert widget.version == "1.0.0"
        assert widget.instance_id == "widget-001"
        assert widget.config == {"paths": ["src/**/*.py"]}

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_widget_validation_success(self):
        """Test valid widget passes validation."""
        widget = ComponentConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001",
            config={},
        )

        errors = widget.validate()
        assert errors == []

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_widget_validation_missing_fields(self):
        """Test validation catches missing fields."""
        widget = ComponentConfig(class_name="", version="", instance_id="", config={})

        errors = widget.validate()
        assert len(errors) == 3
        assert any("class_name is required" in e for e in errors)
        assert any("version is required" in e for e in errors)
        assert any("instance_id is required" in e for e in errors)

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_widget_validation_invalid_class_name(self):
        """Test validation catches invalid class name format."""
        widget = ComponentConfig(
            class_name="bad.module.Widget", version="1.0.0", instance_id="widget-001", config={}
        )

        errors = widget.validate()
        assert len(errors) == 1
        assert "chimera.widgets." in errors[0]


class TestInlineAgentConfig:
    """Tests for InlineAgentConfig."""

    def test_create_inline_agent(self):
        """Test creating an inline agent."""
        agent = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            model_string="openai:gpt-4o",
        )

        assert agent.name == "TestAgent"
        assert agent.description == "A test agent"
        assert agent.base_prompt == "You are a test agent."
        assert agent.model_string == "openai:gpt-4o"

    def test_inline_agent_to_dict(self):
        """Test inline agent serialization."""
        agent_id = str(uuid4())
        agent = InlineAgentConfig(
            id=agent_id,
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            model_string="openai:gpt-4o",
        )

        result = agent.to_dict()

        assert result["type"] == "inline"
        assert result["id"] == agent_id
        assert result["name"] == "TestAgent"
        assert result["basePrompt"] == "You are a test agent."
        assert result["modelString"] == "openai:gpt-4o"

    def test_inline_agent_with_widgets(self):
        """Test inline agent with agent-level widgets."""
        widget = ComponentConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="scratchpad-001",
            config={},
        )

        agent = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            widgets=[widget],
        )

        assert len(agent.widgets) == 1
        assert agent.widgets[0].class_name == "chimera.widgets.ScratchpadWidget"

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_inline_agent_validation(self):
        """Test inline agent validation."""
        agent = InlineAgentConfig(id="", name="", description="A test agent", base_prompt="")

        errors = agent.validate()
        assert len(errors) == 3
        assert any("id is required" in e for e in errors)
        assert any("name is required" in e for e in errors)
        assert any("base_prompt is required" in e for e in errors)


class TestReferencedAgentConfig:
    """Tests for ReferencedAgentConfig."""

    def test_create_referenced_agent(self):
        """Test creating a referenced agent."""
        agent = ReferencedAgentConfig(
            agent_uuid=str(uuid4()), version="2.1.0", overrides={"name": "CustomName"}
        )

        assert agent.version == "2.1.0"
        assert agent.overrides == {"name": "CustomName"}

    def test_referenced_agent_to_dict(self):
        """Test referenced agent serialization."""
        agent_uuid = str(uuid4())
        agent = ReferencedAgentConfig(
            agent_uuid=agent_uuid, version="2.1.0", overrides={"name": "CustomName"}
        )

        result = agent.to_dict()

        assert result["type"] == "reference"
        assert result["agentUuid"] == agent_uuid
        assert result["version"] == "2.1.0"
        assert result["overrides"] == {"name": "CustomName"}

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_referenced_agent_validation_invalid_override(self):
        """Test validation catches invalid override fields."""
        agent = ReferencedAgentConfig(
            agent_uuid=str(uuid4()),
            version="2.1.0",
            overrides={"base_prompt": "Can't override this"},  # Not allowed
        )

        errors = agent.validate()
        assert len(errors) == 1
        assert "Invalid override field" in errors[0]


class TestAgentFromDict:
    """Tests for agent_from_dict() parser."""

    def test_parse_inline_agent(self):
        """Test parsing inline agent from dict."""
        data = {
            "type": "inline",
            "id": str(uuid4()),
            "name": "TestAgent",
            "description": "A test agent",
            "basePrompt": "You are a test agent.",
            "modelString": "openai:gpt-4o",
            "widgets": [],
        }

        agent = agent_from_dict(data)

        assert isinstance(agent, InlineAgentConfig)
        assert agent.name == "TestAgent"

    def test_parse_referenced_agent(self):
        """Test parsing referenced agent from dict."""
        data = {
            "type": "reference",
            "agentUuid": str(uuid4()),
            "version": "2.1.0",
            "overrides": {"name": "CustomName"},
            "widgets": [],
        }

        agent = agent_from_dict(data)

        assert isinstance(agent, ReferencedAgentConfig)
        assert agent.version == "2.1.0"

    def test_parse_invalid_agent_type(self):
        """Test parsing invalid agent type raises error."""
        data = {"type": "unknown"}

        with pytest.raises(ValueError, match="Unknown agent type"):
            agent_from_dict(data)


class TestSpaceConfig:
    """Tests for space configurations."""

    def test_default_space(self):
        """Test default space config."""
        space = DefaultSpaceConfig()

        assert space.widgets == []

    def test_default_space_with_widgets(self):
        """Test default space with space-level widgets."""
        widget = ComponentConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="whiteboard-001",
            config={},
        )

        space = DefaultSpaceConfig(widgets=[widget])

        assert len(space.widgets) == 1
        assert space.widgets[0].class_name == "chimera.widgets.WhiteboardWidget"

    def test_default_space_to_dict(self):
        """Test default space serialization."""
        space = DefaultSpaceConfig()

        result = space.to_dict()

        assert result["type"] == "default"
        assert result["widgets"] == []

    def test_referenced_space(self):
        """Test referenced space config."""
        space = ReferencedSpaceConfig(
            class_name="chimera.spaces.GroupChatSpace",
            version="1.0.0",
            config={"selection_strategy": "round_robin"},
        )

        assert space.class_name == "chimera.spaces.GroupChatSpace"
        assert space.config["selection_strategy"] == "round_robin"

    def test_referenced_space_to_dict(self):
        """Test referenced space serialization."""
        space = ReferencedSpaceConfig(
            class_name="chimera.spaces.GroupChatSpace",
            version="1.0.0",
            config={"selection_strategy": "round_robin"},
        )

        result = space.to_dict()

        assert result["type"] == "reference"
        assert result["className"] == "chimera.spaces.GroupChatSpace"
        assert result["version"] == "1.0.0"
        assert result["config"]["selection_strategy"] == "round_robin"


class TestBlueprint:
    """Tests for Blueprint domain object."""

    def test_create_simple_blueprint(self):
        """Test creating a simple blueprint."""
        blueprint = create_simple_blueprint(
            agent_name="TestAgent",
            agent_prompt="You are a test agent.",
            model_string="openai:gpt-4o",
        )

        # Agents are now nested under space
        assert len(blueprint.space.agents) == 1
        assert isinstance(blueprint.space.agents[0], InlineAgentConfig)
        assert blueprint.space.agents[0].name == "TestAgent"
        assert isinstance(blueprint.space, DefaultSpaceConfig)

    def test_blueprint_to_event(self):
        """Test blueprint serialization to event format."""
        thread_id = str(uuid4())
        agent = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
        )
        # Agents now nested under space
        space = DefaultSpaceConfig(agents=[agent])

        blueprint = Blueprint(thread_id=thread_id, space=space)

        event = blueprint.to_event()

        assert event["type"] == "thread-blueprint"
        assert event["threadId"] == thread_id
        assert event["blueprintVersion"] == "0.0.7"
        assert "timestamp" in event
        assert "blueprint" in event
        assert "space" in event["blueprint"]
        # Agents are nested in space, not at blueprint level
        assert "agents" in event["blueprint"]["space"]

    def test_blueprint_round_trip(self):
        """Test blueprint serialization and deserialization round-trip."""
        thread_id = str(uuid4())
        agent_id = str(uuid4())

        # Agents now nested under space
        original = Blueprint(
            thread_id=thread_id,
            space=DefaultSpaceConfig(
                agents=[
                    InlineAgentConfig(
                        id=agent_id,
                        name="TestAgent",
                        description="A test agent",
                        base_prompt="You are a test agent.",
                        model_string="openai:gpt-4o",
                    )
                ]
            ),
        )

        # Serialize to event
        event = original.to_event()

        # Deserialize from event
        restored = Blueprint.from_event(event)

        assert restored.thread_id == thread_id
        assert len(restored.space.agents) == 1
        assert isinstance(restored.space.agents[0], InlineAgentConfig)
        assert restored.space.agents[0].id == agent_id
        assert restored.space.agents[0].name == "TestAgent"

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_blueprint_validation_no_agents(self):
        """Test validation catches blueprint with no agents."""
        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(agents=[]),  # Agents nested under space
        )

        errors = blueprint.validate()
        assert len(errors) > 0
        assert any("at least one agent" in e for e in errors)

    @pytest.mark.skip(reason="Validation not yet implemented - TODO")
    def test_blueprint_validation_duplicate_widget_ids(self):
        """Test validation catches duplicate widget instance_ids."""
        widget1 = ComponentConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="duplicate-001",
            config={},
        )
        widget2 = ComponentConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="duplicate-001",  # Same ID!
            config={},
        )

        # Agents now nested under space
        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(
                widgets=[widget1],
                agents=[
                    InlineAgentConfig(
                        id=str(uuid4()),
                        name="TestAgent",
                        description="A test agent",
                        base_prompt="You are a test agent.",
                        widgets=[widget2],
                    )
                ],
            ),
        )

        errors = blueprint.validate()
        assert any("Duplicate widget instance_id" in e for e in errors)

    def test_get_widgets_for_agent(self):
        """Test getting widgets for a specific agent."""
        space_widget = ComponentConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="shared-001",
            config={},
        )
        agent_widget = ComponentConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="private-001",
            config={},
        )

        agent_id = str(uuid4())
        agent = InlineAgentConfig(
            id=agent_id,
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            widgets=[agent_widget],
        )

        # Agents now nested under space
        blueprint = Blueprint(
            thread_id=str(uuid4()), space=DefaultSpaceConfig(widgets=[space_widget], agents=[agent])
        )

        widgets = blueprint.get_widgets_for_agent(agent_id)

        assert len(widgets) == 2
        assert widgets[0].instance_id == "shared-001"  # Space widget
        assert widgets[1].instance_id == "private-001"  # Agent widget

    def test_blueprint_with_guardrails(self):
        """Test blueprint with max_turns and max_depth."""
        # Agents now nested under space
        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(
                agents=[
                    InlineAgentConfig(
                        id=str(uuid4()),
                        name="TestAgent",
                        description="A test agent",
                        base_prompt="You are a test agent.",
                    )
                ]
            ),
            max_turns=10,
            max_depth=3,
        )

        event = blueprint.to_event()

        assert event["blueprint"]["maxTurns"] == 10
        assert event["blueprint"]["maxDepth"] == 3

    def test_complex_blueprint_with_multiple_agents_and_widgets(self):
        """Test complex blueprint with multiple agents and widget scoping."""
        # Space-level widgets (shared)
        shared_whiteboard = ComponentConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="shared-whiteboard-001",
            config={},
        )

        # Agent 1 - private widgets
        agent1_scratchpad = ComponentConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="agent1-scratchpad",
            config={},
        )

        # Agent 2 - private widgets
        agent2_scratchpad = ComponentConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="agent2-scratchpad",
            config={},
        )

        agent1 = InlineAgentConfig(
            id=str(uuid4()),
            name="Agent1",
            description="First agent",
            base_prompt="You are agent 1.",
            widgets=[agent1_scratchpad],
        )

        agent2 = InlineAgentConfig(
            id=str(uuid4()),
            name="Agent2",
            description="Second agent",
            base_prompt="You are agent 2.",
            widgets=[agent2_scratchpad],
        )

        # Agents now nested under space
        space = ReferencedSpaceConfig(
            class_name="chimera.spaces.GroupChatSpace",
            version="1.0.0",
            agents=[agent1, agent2],  # Agents nested here
            config={"selection_strategy": "round_robin"},
            widgets=[shared_whiteboard],
        )

        blueprint = Blueprint(thread_id=str(uuid4()), space=space)

        # Test round-trip
        event = blueprint.to_event()
        restored = Blueprint.from_event(event)

        # Agents now accessed via space
        assert len(restored.space.agents) == 2
        assert isinstance(restored.space, ReferencedSpaceConfig)
        assert len(restored.space.widgets) == 1  # Shared whiteboard
        assert len(restored.space.agents[0].widgets) == 1  # Agent1 scratchpad
        assert len(restored.space.agents[1].widgets) == 1  # Agent2 scratchpad


class TestBlueprintVersionValidation:
    """Tests for ThreadProtocol version validation in Blueprint."""

    def test_blueprint_to_event_includes_version(self):
        """Blueprint.to_event() includes threadProtocolVersion field."""
        from chimera_core.threadprotocol.blueprint import THREAD_PROTOCOL_VERSION

        blueprint = create_simple_blueprint(agent_name="Test Agent", agent_prompt="Test prompt")

        event = blueprint.to_event()

        # Check that version field is present
        assert "threadProtocolVersion" in event
        assert event["threadProtocolVersion"] == THREAD_PROTOCOL_VERSION
        # Separate from blueprintVersion
        assert "blueprintVersion" in event
        assert event["blueprintVersion"] == "0.0.7"

    def test_blueprint_from_event_with_matching_version(self):
        """Blueprint.from_event() succeeds with matching version."""
        from chimera_core.threadprotocol.blueprint import THREAD_PROTOCOL_VERSION

        event = {
            "type": "thread-blueprint",
            "threadId": str(uuid4()),
            "threadProtocolVersion": THREAD_PROTOCOL_VERSION,
            "blueprintVersion": "0.0.7",
            "blueprint": {
                "space": {
                    "type": "default",
                    "agents": [
                        {
                            "type": "inline",
                            "id": "agent-1",
                            "name": "Test",
                            "description": "Test agent",
                            "basePrompt": "You are helpful",
                            "widgets": [],
                        }
                    ],
                    "widgets": [],
                }
            },
        }

        # Should parse successfully
        blueprint = Blueprint.from_event(event)

        assert blueprint.thread_id == event["threadId"]
        assert len(blueprint.space.agents) == 1

    def test_blueprint_from_event_with_version_mismatch(self):
        """Blueprint.from_event() raises error on version mismatch."""
        event = {
            "type": "thread-blueprint",
            "threadId": str(uuid4()),
            "threadProtocolVersion": "0.0.1",  # Incompatible version
            "blueprintVersion": "0.0.7",
            "blueprint": {"space": {"type": "default", "agents": [], "widgets": []}},
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="ThreadProtocol version mismatch"):
            Blueprint.from_event(event)

    def test_blueprint_from_event_with_missing_version(self):
        """Blueprint.from_event() raises error when version field missing."""
        event = {
            "type": "thread-blueprint",
            "threadId": str(uuid4()),
            # No threadProtocolVersion field (old format)
            "blueprintVersion": "0.0.7",
            "blueprint": {"space": {"type": "default", "agents": [], "widgets": []}},
        }

        # Should raise ValueError (defaults to 0.0.1 which doesn't match)
        with pytest.raises(ValueError, match="ThreadProtocol version mismatch"):
            Blueprint.from_event(event)

    def test_blueprint_roundtrip_preserves_version(self):
        """Blueprint roundtrip (to_event → from_event) preserves version."""
        from chimera_core.threadprotocol.blueprint import THREAD_PROTOCOL_VERSION

        original = create_simple_blueprint(agent_name="Test Agent", agent_prompt="Test prompt")

        # Convert to event and back
        event = original.to_event()
        restored = Blueprint.from_event(event)

        # Version should be preserved through roundtrip
        assert event["threadProtocolVersion"] == THREAD_PROTOCOL_VERSION

        # Restored blueprint should have same thread_id
        assert restored.thread_id == original.thread_id
