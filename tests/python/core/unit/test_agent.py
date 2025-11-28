"""Tests for Agent class - loading from YAML and serialization."""

from uuid import uuid4

import pytest

from chimera_core.agent import Agent
from chimera_core.threadprotocol.blueprint import InlineAgentConfig


@pytest.mark.skip(reason="Fixture file tests/python/fixtures/agents/jarvis.yaml not in repo")
def test_agent_from_yaml():
    """Test loading agent from YAML file."""
    yaml_path = "tests/python/fixtures/agents/jarvis.yaml"

    agent = Agent.from_yaml(yaml_path)

    # Verify basic fields
    assert agent.name == "Jarvis"
    assert agent.id == "e9c226ce-2736-4bd7-be3a-f9b31550cec6"
    assert agent.description == "Your own personal Jarvis."
    assert "You are Jarvis" in agent.base_prompt

    # Verify metadata extracted
    assert "voice_id" in agent.metadata
    assert agent.metadata["voice_id"] == "0KYw5BqNtUJmEkwDENbP"


def test_agent_from_yaml_missing_file():
    """Test that loading from non-existent file raises error."""
    with pytest.raises(FileNotFoundError):
        Agent.from_yaml("nonexistent.yaml")


def test_agent_register_widget():
    """Test widget registration."""
    agent = Agent(id=str(uuid4()), name="TestAgent", base_prompt="Test prompt")

    # Mock widget (just needs to be an object)
    class MockWidget:
        def to_blueprint_config(self):
            return {"mock": "widget"}

    widget1 = MockWidget()
    widget2 = MockWidget()

    agent.register_widget(widget1)
    assert len(agent.widgets) == 1

    agent.register_widget(widget2)
    assert len(agent.widgets) == 2

    # Registering same widget twice shouldn't duplicate
    agent.register_widget(widget1)
    assert len(agent.widgets) == 2


def test_agent_to_blueprint_config():
    """Test serialization to BlueprintProtocol."""
    agent_id = str(uuid4())
    agent = Agent(
        id=agent_id,
        name="TestAgent",
        base_prompt="You are a test agent.",
        description="A test agent for testing",
        model_string="openai:gpt-4o-mini",
    )

    config = agent.to_blueprint_config()

    # Verify it's the right type
    assert isinstance(config, InlineAgentConfig)

    # Verify all fields transferred correctly
    assert config.id == agent_id
    assert config.name == "TestAgent"
    assert config.base_prompt == "You are a test agent."
    assert config.description == "A test agent for testing"
    assert config.model_string == "openai:gpt-4o-mini"
    assert config.widgets == []


@pytest.mark.skip(reason="Fixture file tests/python/fixtures/agents/jarvis.yaml not in repo")
def test_agent_round_trip_serialization():
    """Test that YAML → Agent → BlueprintConfig preserves data."""
    yaml_path = "tests/python/fixtures/agents/jarvis.yaml"

    # Load from YAML
    agent = Agent.from_yaml(yaml_path)

    # Serialize to blueprint config
    config = agent.to_blueprint_config()

    # Verify data preserved
    assert config.id == agent.id
    assert config.name == agent.name
    assert config.base_prompt == agent.base_prompt
    assert config.description == agent.description

    # Serialize to dict (for ThreadProtocol)
    config_dict = config.to_dict()

    # Verify dict structure
    assert config_dict["type"] == "inline"
    assert config_dict["id"] == agent.id
    assert config_dict["name"] == "Jarvis"
    assert "You are Jarvis" in config_dict["basePrompt"]
