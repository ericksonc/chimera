"""Tests for SpaceFactory.

SpaceFactory is the central routing logic for creating Space instances from
BlueprintProtocol configuration. These tests verify:
- DefaultSpaceConfig routes to GenericSpace
- ReferencedSpaceConfig routes to specified class
- Unknown config types raise ValueError
"""

from uuid import uuid4

import pytest

from chimera_core.spaces.factory import SpaceFactory
from chimera_core.spaces.generic_space import GenericSpace
from chimera_core.threadprotocol.blueprint import (
    DefaultSpaceConfig,
    InlineAgentConfig,
    ReferencedSpaceConfig,
)


class TestSpaceFactoryRouting:
    """Tests for SpaceFactory routing logic."""

    def test_default_config_creates_generic_space(self):
        """DefaultSpaceConfig routes to GenericSpace."""
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
        )
        space_config = DefaultSpaceConfig(agents=[agent_config])

        space = SpaceFactory.from_blueprint_config(space_config)

        assert isinstance(space, GenericSpace)
        assert space.active_agent.name == "TestAgent"

    def test_referenced_config_loads_specified_class(self):
        """ReferencedSpaceConfig loads the specified Space class."""
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
        )
        space_config = ReferencedSpaceConfig(
            class_name="chimera_core.spaces.GenericSpace",  # Use GenericSpace for testing
            version="1.0.0",
            config={},
            agents=[agent_config],
        )

        space = SpaceFactory.from_blueprint_config(space_config)

        assert isinstance(space, GenericSpace)

    def test_unknown_config_type_raises_error(self):
        """Unknown config type raises ValueError."""

        class UnknownSpaceConfig:
            """A config type the factory doesn't know about."""

            pass

        unknown_config = UnknownSpaceConfig()

        with pytest.raises(ValueError, match="Unknown space config type"):
            SpaceFactory.from_blueprint_config(unknown_config)

    def test_invalid_class_name_raises_error(self):
        """Invalid class name in ReferencedSpaceConfig raises error."""
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="TestAgent",
            description="A test agent",
            base_prompt="You are a test agent.",
        )
        space_config = ReferencedSpaceConfig(
            class_name="nonexistent.module.FakeSpace",
            version="1.0.0",
            config={},
            agents=[agent_config],
        )

        with pytest.raises((ValueError, ModuleNotFoundError)):
            SpaceFactory.from_blueprint_config(space_config)


class TestSpaceFactoryAgentResolution:
    """Tests for agent resolution through SpaceFactory."""

    def test_single_agent_resolved(self):
        """Single inline agent is properly resolved."""
        agent_id = str(uuid4())
        agent_config = InlineAgentConfig(
            id=agent_id,
            name="SingleAgent",
            description="A single agent",
            base_prompt="You are a single agent.",
            model_string="openai:gpt-4o",
        )
        space_config = DefaultSpaceConfig(agents=[agent_config])

        space = SpaceFactory.from_blueprint_config(space_config)

        assert space.active_agent.id == agent_id
        assert space.active_agent.name == "SingleAgent"
        assert space.active_agent.base_prompt == "You are a single agent."

    def test_agent_with_widgets_preserved(self):
        """Agent widgets are preserved through factory."""
        from chimera_core.threadprotocol.blueprint import ComponentConfig

        widget_config = ComponentConfig(
            class_name="chimera_core.widgets.qa_widget.QAWidget",  # Full module path
            version="1.0.0",
            instance_id="qa-widget-001",
            config={},
        )
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="WidgetAgent",
            description="An agent with widgets",
            base_prompt="You have widgets.",
            widgets=[widget_config],
        )
        space_config = DefaultSpaceConfig(agents=[agent_config])

        space = SpaceFactory.from_blueprint_config(space_config)

        # The agent should have been resolved with its widgets
        assert space.active_agent.name == "WidgetAgent"
        # Verify widget was hydrated
        assert len(space.active_agent.widgets) == 1


class TestSpaceFactoryWithRealSpaces:
    """Tests using real Space implementations."""

    def test_graph_space_can_be_loaded(self):
        """GraphSpace can be loaded via ReferencedSpaceConfig."""
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="GraphAgent",
            description="An agent for graph space",
            base_prompt="You are a graph agent.",
        )
        space_config = ReferencedSpaceConfig(
            class_name="chimera_core.spaces.GraphSpace",
            version="1.0.0",
            config={},
            agents=[agent_config],
        )

        from chimera_core.spaces.graph_space import GraphSpace

        space = SpaceFactory.from_blueprint_config(space_config)

        assert isinstance(space, GraphSpace)

    def test_cron_summarizer_space_can_be_loaded(self):
        """CronSummarizerSpace can be loaded via ReferencedSpaceConfig."""
        agent_config = InlineAgentConfig(
            id=str(uuid4()),
            name="SummarizerAgent",
            description="An agent for summarization",
            base_prompt="You summarize documents.",
        )
        space_config = ReferencedSpaceConfig(
            class_name="chimera_core.spaces.CronSummarizerSpace",
            version="1.0.0",
            config={
                "prompt": "Summarize documents",
                "base_path": "/tmp",
                "input_directory": "inbox",
                "output_directory": "out",
            },
            agents=[agent_config],
        )

        from chimera_core.spaces.cron_summarizer_space import CronSummarizerSpace

        space = SpaceFactory.from_blueprint_config(space_config)

        assert isinstance(space, CronSummarizerSpace)
