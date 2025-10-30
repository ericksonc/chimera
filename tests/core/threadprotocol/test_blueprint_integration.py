"""Integration tests for Blueprint with ThreadProtocol writer/reader."""

import pytest
import tempfile
from pathlib import Path
from uuid import uuid4

from core.threadprotocol.blueprint import (
    Blueprint,
    InlineAgentConfig,
    DefaultSpaceConfig,
    ComponentConfig,
    create_simple_blueprint,
)
from core.threadprotocol.writer import ThreadProtocolWriter
from core.threadprotocol.reader import ThreadProtocolReader


class TestBlueprintWriterIntegration:
    """Test Blueprint integration with ThreadProtocol writer/reader."""

    @pytest.mark.asyncio
    async def test_write_and_read_simple_blueprint(self):
        """Test writing and reading a simple blueprint."""
        # Create a simple blueprint
        blueprint = create_simple_blueprint(
            agent_name="TestAgent",
            agent_prompt="You are a test agent.",
            model_string="openai:gpt-4o"
        )

        # Create temporary file
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_thread.jsonl"

            # Write blueprint as Line 1
            async with ThreadProtocolWriter(file_path) as writer:
                event = blueprint.to_event()
                await writer.write_event(event)

            # Read it back
            reader = ThreadProtocolReader(file_path)
            blueprint_event = reader.read_blueprint()

            assert blueprint_event is not None
            assert blueprint_event["event_type"] == "thread_blueprint"
            assert blueprint_event["thread_id"] == blueprint.thread_id

            # Parse back to Blueprint object
            restored = Blueprint.from_event(blueprint_event)

            assert restored.thread_id == blueprint.thread_id
            assert len(restored.agents) == 1
            assert isinstance(restored.agents[0], InlineAgentConfig)

    @pytest.mark.asyncio
    async def test_write_blueprint_then_events(self):
        """Test writing blueprint followed by other events."""
        blueprint = create_simple_blueprint()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_thread.jsonl"

            # Write blueprint and some events
            async with ThreadProtocolWriter(file_path) as writer:
                # Line 1: Blueprint
                await writer.write_event(blueprint.to_event())

                # Line 2+: Other events
                await writer.write_event({
                    "event_type": "user_turn_start"
                })
                await writer.write_event({
                    "event_type": "user_message",
                    "content": "Hello!"
                })

            # Read back
            reader = ThreadProtocolReader(file_path)

            # Check blueprint is Line 1
            blueprint_event = reader.read_blueprint()
            assert blueprint_event is not None

            # Check all events
            all_events = list(reader.read_all())
            assert len(all_events) == 3
            assert all_events[0]["event_type"] == "thread_blueprint"
            assert all_events[1]["event_type"] == "user_turn_start"
            assert all_events[2]["event_type"] == "user_message"

    @pytest.mark.asyncio
    async def test_complex_blueprint_integration(self):
        """Test complex blueprint with widgets at both levels."""
        # Space-level widget
        shared_widget = ComponentConfig(
            class_name="chimera.widgets.WhiteboardWidget",
            version="1.0.0",
            instance_id="shared-001"
        )

        # Agent-level widget
        private_widget = ComponentConfig(
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
            widgets=[private_widget]
        )

        space = DefaultSpaceConfig(widgets=[shared_widget])

        blueprint = Blueprint(
            thread_id=str(uuid4()),
            space=space,
            agents=[agent],
            max_turns=10
        )

        # Validate before writing
        errors = blueprint.validate()
        assert errors == []

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_thread.jsonl"

            # Write
            async with ThreadProtocolWriter(file_path) as writer:
                await writer.write_event(blueprint.to_event())

            # Read and parse
            reader = ThreadProtocolReader(file_path)
            event = reader.read_blueprint()
            restored = Blueprint.from_event(event)

            # Verify structure
            assert restored.max_turns == 10
            assert len(restored.space.widgets) == 1
            assert restored.space.widgets[0].instance_id == "shared-001"
            assert len(restored.agents[0].widgets) == 1
            assert restored.agents[0].widgets[0].instance_id == "private-001"

            # Verify get_widgets_for_agent works
            widgets = restored.get_widgets_for_agent(agent_id)
            assert len(widgets) == 2
            assert widgets[0].instance_id == "shared-001"  # Space widget
            assert widgets[1].instance_id == "private-001"  # Agent widget


class TestBlueprintWithWriter:
    """Test using ThreadProtocolWriter convenience methods with Blueprint."""

    @pytest.mark.asyncio
    async def test_write_blueprint_method(self):
        """Test ThreadProtocolWriter.write_blueprint() still works."""
        blueprint = create_simple_blueprint()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_thread.jsonl"

            async with ThreadProtocolWriter(file_path) as writer:
                # Use the convenience method
                await writer.write_blueprint(
                    thread_id=blueprint.thread_id,
                    blueprint=blueprint.to_event()["blueprint"]
                )

            # Read it back
            reader = ThreadProtocolReader(file_path)
            event = reader.read_blueprint()

            assert event is not None
            assert event["event_type"] == "thread_blueprint"
            assert event["thread_id"] == blueprint.thread_id
