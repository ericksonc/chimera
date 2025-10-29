"""Tests for BlueprintProtocol domain objects."""

import pytest
from uuid import uuid4

from core.threadprotocol.blueprint import (
    Blueprint,
    InlineAgentConfig,
    ReferencedAgentConfig,
    DefaultSpaceConfig,
    ReferencedSpaceConfig,
    WidgetConfig,
    create_simple_blueprint,
    agent_from_dict,
    space_from_dict,
)


class TestWidgetConfig:
    """Tests for WidgetConfig."""

    def test_create_widget_config(self):
        """Test creating a widget config."""
        widget = WidgetConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001",
            config={"paths": ["src/**/*.py"]}
        )

        assert widget.class_name == "chimera.widgets.CodeWindowWidget"
        assert widget.version == "1.0.0"
        assert widget.instance_id == "widget-001"
        assert widget.config == {"paths": ["src/**/*.py"]}

    def test_widget_to_dict(self):
        """Test widget serialization."""
        widget = WidgetConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001",
            config={"paths": ["src/**/*.py"]}
        )

        result = widget.to_dict()

        assert result == {
            "class_name": "chimera.widgets.CodeWindowWidget",
            "version": "1.0.0",
            "instance_id": "widget-001",
            "config": {"paths": ["src/**/*.py"]}
        }

    def test_widget_from_dict(self):
        """Test widget deserialization."""
        data = {
            "class_name": "chimera.widgets.CodeWindowWidget",
            "version": "1.0.0",
            "instance_id": "widget-001",
            "config": {"paths": ["src/**/*.py"]}
        }

        widget = WidgetConfig.from_dict(data)

        assert widget.class_name == "chimera.widgets.CodeWindowWidget"
        assert widget.version == "1.0.0"
        assert widget.instance_id == "widget-001"
        assert widget.config == {"paths": ["src/**/*.py"]}

    def test_widget_validation_success(self):
        """Test valid widget passes validation."""
        widget = WidgetConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="widget-001"
        )

        errors = widget.validate()
        assert errors == []

    def test_widget_validation_missing_fields(self):
        """Test validation catches missing fields."""
        widget = WidgetConfig(
            class_name="",
            version="",
            instance_id=""
        )

        errors = widget.validate()
        assert len(errors) == 3
        assert any("class_name is required" in e for e in errors)
        assert any("version is required" in e for e in errors)
        assert any("instance_id is required" in e for e in errors)

    def test_widget_validation_invalid_class_name(self):
        """Test validation catches invalid class name format."""
        widget = WidgetConfig(
            class_name="bad.module.Widget",
            version="1.0.0",
            instance_id="widget-001"
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
            model_string="openai:gpt-4o"
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
            model_string="openai:gpt-4o"
        )

        result = agent.to_dict()

        assert result["type"] == "inline"
        assert result["id"] == agent_id
        assert result["name"] == "TestAgent"
        assert result["base_prompt"] == "You are a test agent."
        assert result["model_string"] == "openai:gpt-4o"

    def test_inline_agent_with_widgets(self):
        """Test inline agent with agent-level widgets."""
        widget = WidgetConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="scratchpad-001"
        )

        agent = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            widgets=[widget]
        )

        assert len(agent.widgets) == 1
        assert agent.widgets[0].class_name == "chimera.widgets.ScratchpadWidget"

    def test_inline_agent_validation(self):
        """Test inline agent validation."""
        agent = InlineAgentConfig(
            id="",
            name="",
            description="A test agent",
            base_prompt=""
        )

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
            agent_uuid=str(uuid4()),
            version="2.1.0",
            overrides={"name": "CustomName"}
        )

        assert agent.version == "2.1.0"
        assert agent.overrides == {"name": "CustomName"}

    def test_referenced_agent_to_dict(self):
        """Test referenced agent serialization."""
        agent_uuid = str(uuid4())
        agent = ReferencedAgentConfig(
            agent_uuid=agent_uuid,
            version="2.1.0",
            overrides={"name": "CustomName"}
        )

        result = agent.to_dict()

        assert result["type"] == "reference"
        assert result["agent_uuid"] == agent_uuid
        assert result["version"] == "2.1.0"
        assert result["overrides"] == {"name": "CustomName"}

    def test_referenced_agent_validation_invalid_override(self):
        """Test validation catches invalid override fields."""
        agent = ReferencedAgentConfig(
            agent_uuid=str(uuid4()),
            version="2.1.0",
            overrides={"base_prompt": "Can't override this"}  # Not allowed
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
            "base_prompt": "You are a test agent.",
            "model_string": "openai:gpt-4o",
            "widgets": []
        }

        agent = agent_from_dict(data)

        assert isinstance(agent, InlineAgentConfig)
        assert agent.name == "TestAgent"

    def test_parse_referenced_agent(self):
        """Test parsing referenced agent from dict."""
        data = {
            "type": "reference",
            "agent_uuid": str(uuid4()),
            "version": "2.1.0",
            "overrides": {"name": "CustomName"},
            "widgets": []
        }

        agent = agent_from_dict(data)

        assert isinstance(agent, ReferencedAgentConfig)
        assert agent.version == "2.1.0"

    def test_parse_invalid_agent_type(self):
        """Test parsing invalid agent type raises error."""
        data = {
            "type": "unknown"
        }

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
        widget = WidgetConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="whiteboard-001"
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
            config={"selection_strategy": "round_robin"}
        )

        assert space.class_name == "chimera.spaces.GroupChatSpace"
        assert space.config["selection_strategy"] == "round_robin"

    def test_referenced_space_to_dict(self):
        """Test referenced space serialization."""
        space = ReferencedSpaceConfig(
            class_name="chimera.spaces.GroupChatSpace",
            version="1.0.0",
            config={"selection_strategy": "round_robin"}
        )

        result = space.to_dict()

        assert result["type"] == "reference"
        assert result["class_name"] == "chimera.spaces.GroupChatSpace"
        assert result["version"] == "1.0.0"
        assert result["config"]["selection_strategy"] == "round_robin"


class TestBlueprint:
    """Tests for Blueprint domain object."""

    def test_create_simple_blueprint(self):
        """Test creating a simple blueprint."""
        blueprint = create_simple_blueprint(
            agent_name="TestAgent",
            agent_prompt="You are a test agent.",
            model_string="openai:gpt-4o"
        )

        assert len(blueprint.agents) == 1
        assert isinstance(blueprint.agents[0], InlineAgentConfig)
        assert blueprint.agents[0].name == "TestAgent"
        assert isinstance(blueprint.space, DefaultSpaceConfig)

    def test_blueprint_to_event(self):
        """Test blueprint serialization to event format."""
        thread_id = str(uuid4())
        agent = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent."
        )
        space = DefaultSpaceConfig()

        blueprint = Blueprint(
            thread_id=thread_id,
            space=space,
            agents=[agent]
        )

        event = blueprint.to_event()

        assert event["event_type"] == "thread_blueprint"
        assert event["thread_id"] == thread_id
        assert event["blueprint_version"] == "0.0.1"
        assert "timestamp" in event
        assert "blueprint" in event
        assert "space" in event["blueprint"]
        assert "agents" in event["blueprint"]

    def test_blueprint_round_trip(self):
        """Test blueprint serialization and deserialization round-trip."""
        thread_id = str(uuid4())
        agent_id = str(uuid4())

        original = Blueprint(
            thread_id=thread_id,
            space=DefaultSpaceConfig(),
            agents=[
                InlineAgentConfig(
                    id=agent_id,
                    name="TestAgent",
                    description="A test agent",
                    base_prompt="You are a test agent.",
                    model_string="openai:gpt-4o"
                )
            ]
        )

        # Serialize to event
        event = original.to_event()

        # Deserialize from event
        restored = Blueprint.from_event(event)

        assert restored.thread_id == thread_id
        assert len(restored.agents) == 1
        assert isinstance(restored.agents[0], InlineAgentConfig)
        assert restored.agents[0].id == agent_id
        assert restored.agents[0].name == "TestAgent"

    def test_blueprint_validation_no_agents(self):
        """Test validation catches blueprint with no agents."""
        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(),
            agents=[]
        )

        errors = blueprint.validate()
        assert len(errors) > 0
        assert any("at least one agent" in e for e in errors)

    def test_blueprint_validation_duplicate_widget_ids(self):
        """Test validation catches duplicate widget instance_ids."""
        widget1 = WidgetConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="duplicate-001"
        )
        widget2 = WidgetConfig(
            class_name="chimera.widgets.CodeWindowWidget",
            version="1.0.0",
            instance_id="duplicate-001"  # Same ID!
        )

        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(widgets=[widget1]),
            agents=[
                InlineAgentConfig(
                    id=str(uuid4()),
                    name="TestAgent",
                    description="A test agent",
                    base_prompt="You are a test agent.",
                    widgets=[widget2]
                )
            ]
        )

        errors = blueprint.validate()
        assert any("Duplicate widget instance_id" in e for e in errors)

    def test_get_widgets_for_agent(self):
        """Test getting widgets for a specific agent."""
        space_widget = WidgetConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="shared-001"
        )
        agent_widget = WidgetConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="private-001"
        )

        agent_id = str(uuid4())
        agent = InlineAgentConfig(
            id=agent_id,
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
            widgets=[agent_widget]
        )

        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(widgets=[space_widget]),
            agents=[agent]
        )

        widgets = blueprint.get_widgets_for_agent(agent_id)

        assert len(widgets) == 2
        assert widgets[0].instance_id == "shared-001"  # Space widget
        assert widgets[1].instance_id == "private-001"  # Agent widget

    def test_blueprint_with_guardrails(self):
        """Test blueprint with max_turns and max_depth."""
        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=DefaultSpaceConfig(),
            agents=[
                InlineAgentConfig(
                    id=str(uuid4()),
                    name="TestAgent",
                    description="A test agent",
                    base_prompt="You are a test agent."
                )
            ],
            max_turns=10,
            max_depth=3
        )

        event = blueprint.to_event()

        assert event["blueprint"]["max_turns"] == 10
        assert event["blueprint"]["max_depth"] == 3

    def test_complex_blueprint_with_multiple_agents_and_widgets(self):
        """Test complex blueprint with multiple agents and widget scoping."""
        # Space-level widgets (shared)
        shared_whiteboard = WidgetConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="shared-whiteboard-001"
        )

        # Agent 1 - private widgets
        agent1_scratchpad = WidgetConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="agent1-scratchpad"
        )

        # Agent 2 - private widgets
        agent2_scratchpad = WidgetConfig(
            class_name="chimera.widgets.ScratchpadWidget",
            version="1.0.0",
            instance_id="agent2-scratchpad"
        )

        agent1 = InlineAgentConfig(
            id=str(uuid4()),
            name="Agent1",
            description="First agent",
            base_prompt="You are agent 1.",
            widgets=[agent1_scratchpad]
        )

        agent2 = InlineAgentConfig(
            id=str(uuid4()),
            name="Agent2",
            description="Second agent",
            base_prompt="You are agent 2.",
            widgets=[agent2_scratchpad]
        )

        space = ReferencedSpaceConfig(
            class_name="chimera.spaces.GroupChatSpace",
            version="1.0.0",
            config={"selection_strategy": "round_robin"},
            widgets=[shared_whiteboard]
        )

        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=space,
            agents=[agent1, agent2]
        )

        # Validate no errors
        errors = blueprint.validate()
        assert errors == []

        # Test round-trip
        event = blueprint.to_event()
        restored = Blueprint.from_event(event)

        assert len(restored.agents) == 2
        assert isinstance(restored.space, ReferencedSpaceConfig)
        assert len(restored.space.widgets) == 1  # Shared whiteboard
        assert len(restored.agents[0].widgets) == 1  # Agent1 scratchpad
        assert len(restored.agents[1].widgets) == 1  # Agent2 scratchpad
