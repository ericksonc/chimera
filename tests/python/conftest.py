"""Shared pytest fixtures for Chimera tests.

This module provides reusable fixtures for testing without heavy mocking:
- mock_thread_deps: ThreadDeps with event capture
- test_model: TestModel for LLM-free agent testing
- simple_agent: Basic Agent instance
- blueprint_builder: Fluent API for building test blueprints
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pydantic_ai.models
import pytest
from pydantic_ai.models.test import TestModel

from chimera_core.thread import ThreadDeps
from chimera_core.threadprotocol.writer import NoOpThreadProtocolWriter

# Global safety: Prevent accidental LLM API calls in tests
# Tests must explicitly use TestModel or FunctionModel for deterministic behavior
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False

from chimera_core.agent import Agent  # noqa: E402
from chimera_core.threadprotocol.blueprint import Blueprint, DefaultSpaceConfig  # noqa: E402


@pytest.fixture
def mock_thread_deps():
    """ThreadDeps with event capture for testing.

    Captures both ThreadProtocol and VSP events for assertions.
    Events are stored in lists attached to the deps object:
    - deps.emitted_threadprotocol: list[dict]
    - deps.emitted_vsp: list[tuple[bool, dict]]  # (include_thread_id, event)

    Example:
        def test_something(mock_thread_deps):
            # ... run code that emits events

            # Check VSP events
            assert len(mock_thread_deps.emitted_vsp) == 2
            include_thread_id, event = mock_thread_deps.emitted_vsp[0]
            assert include_thread_id  # Boundary event
            assert event["type"] == "start"
    """
    emitted_threadprotocol = []
    emitted_vsp = []

    async def capture_threadprotocol(event: dict) -> None:
        emitted_threadprotocol.append(event)

    async def capture_vsp(event: dict, include_thread_id: bool = True) -> None:
        emitted_vsp.append((include_thread_id, event))

    # Create no-op writer for tests (no disk persistence needed)
    thread_writer = NoOpThreadProtocolWriter()

    deps = ThreadDeps(
        emit_threadprotocol_event=capture_threadprotocol,
        emit_vsp_event=capture_vsp,
        thread_writer=thread_writer,
    )

    # Attach lists for easy access in tests
    deps.emitted_threadprotocol = emitted_threadprotocol
    deps.emitted_vsp = emitted_vsp

    return deps


@pytest.fixture
def noop_deps():
    """ThreadDeps with no-op emit functions.

    Use when you don't care about event emission (just need deps).
    For event assertions, use mock_thread_deps instead.
    """

    async def noop_emit_threadprotocol(event: dict) -> None:
        pass

    async def noop_emit_vsp(event: dict, include_thread_id: bool = True) -> None:
        pass

    # Create no-op writer for tests (no disk persistence needed)
    thread_writer = NoOpThreadProtocolWriter()

    return ThreadDeps(
        emit_threadprotocol_event=noop_emit_threadprotocol,
        emit_vsp_event=noop_emit_vsp,
        thread_writer=thread_writer,
    )


@pytest.fixture
def test_model():
    """TestModel for LLM-free agent testing.

    By default, TestModel:
    - Calls ALL registered tools
    - Generates valid test data based on type hints
    - Returns deterministic responses

    Customize behavior in your test:
        test_model = TestModel(custom_result_text="Hello")
        test_model = TestModel(call_tools=["specific_tool"])
    """
    return TestModel()


@pytest.fixture
def simple_agent():
    """Basic Agent instance for testing.

    Returns a minimal agent with:
    - id: "test-agent-001"
    - name: "TestAgent"
    - base_prompt: "You are a test agent."
    - No widgets, no model override

    Customize in your test if needed:
        agent = simple_agent
        agent.register_widget(my_widget)
    """
    return Agent(
        id="test-agent-001",
        name="TestAgent",
        base_prompt="You are a test agent.",
        description="A simple agent for testing",
        identifier="test",
    )


@pytest.fixture
def blueprint_builder():
    """Factory for building test blueprints programmatically.

    Returns a callable that builds Blueprint instances.

    Example:
        blueprint = blueprint_builder(
            agents=[agent1, agent2],
            space_type="RosterSpace",
            space_config={"initial_agent": "agent1"}
        )

    Args:
        agents: List of Agent instances
        space_type: Space class name (e.g., "RosterSpace")
        space_config: Dict of space-specific config
        widgets: Optional list of space-level widgets

    Returns:
        Blueprint instance
    """

    def _build(
        agents: list[Agent] = None,
        space_type: str = "RosterSpace",
        space_config: dict[str, Any] = None,
        widgets: list = None,
    ) -> Blueprint:
        """Build a Blueprint for testing.

        Args:
            agents: List of Agent instances (defaults to [simple_agent])
            space_type: Space class name
            space_config: Space configuration dict
            widgets: Space-level widget configs

        Returns:
            Blueprint instance
        """
        # Default to single test agent
        if agents is None:
            agents = [
                Agent(
                    id="test-agent-001",
                    name="TestAgent",
                    base_prompt="You are a test agent.",
                    description="A test agent",
                    identifier="test",
                )
            ]

        # Serialize agents
        agent_configs = [agent.to_blueprint_config() for agent in agents]

        # Build space config
        space_dict = {"type": space_type}
        if space_config:
            space_dict.update(space_config)

        space_cfg = DefaultSpaceConfig(**space_dict)

        return Blueprint(agents=agent_configs, space=space_cfg, widgets=widgets or [])

    return _build


@pytest.fixture
def test_thread_fixture():
    """Load test_thread.jsonl fixture with blueprint and history.

    Returns:
        Tuple of (blueprint_dict, history_events)

    The fixture contains:
    - Blueprint with RosterSpace and 2 agents (jarvis, unreal)
    - History with agent switching mutations (jarvis -> unreal)
    """
    fixture_path = Path("tests/python/fixtures/agents/test_thread.jsonl")
    with open(fixture_path) as f:
        events = [json.loads(line) for line in f]

    blueprint = events[0]["blueprint"]
    history_events = events[1:]

    return blueprint, history_events


# Common test IDs
TEST_THREAD_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
