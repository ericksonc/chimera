"""Tests for Space.output_type property and Agent integration.

This tests the new output_type property added to Space ABC that allows
spaces to control what types agents can return. This is a prerequisite
for GraphSpace but doesn't affect existing spaces (they all use str).
"""

from typing import List

from pydantic import BaseModel

from chimera_core.agent import Agent
from chimera_core.spaces.base import Space
from chimera_core.spaces.generic_space import GenericSpace


class TestSpaceOutputTypeProperty:
    """Test that Space.output_type property exists and has correct defaults."""

    def test_space_default_output_type_is_str(self):
        """Space ABC should default output_type to str."""
        # GenericSpace is a concrete implementation of Space
        space = GenericSpace()

        assert hasattr(space, "output_type"), "Space should have output_type property"
        assert space.output_type is str, "Default output_type should be str"

    def test_custom_space_can_override_output_type(self):
        """Custom Space implementations can override output_type."""

        class IntOutputSpace(Space):
            """Test space that returns int."""

            @property
            def output_type(self):
                return int

            @property
            def active_agent(self):
                return self._agents[0] if self._agents else None

            def get_transformer(self):
                from chimera_core.threadprotocol.transformer import GenericTransformer

                return GenericTransformer()

            def _get_all_agents(self):
                return self._agents

        space = IntOutputSpace()
        assert space.output_type is int, "Custom space should override output_type"

    def test_custom_space_can_return_list_of_types(self):
        """Custom Space can return list of output types (union)."""

        class MultiOutputSpace(Space):
            """Test space that returns union of types."""

            @property
            def output_type(self):
                return [int, float, str]

            @property
            def active_agent(self):
                return self._agents[0] if self._agents else None

            def get_transformer(self):
                from chimera_core.threadprotocol.transformer import GenericTransformer

                return GenericTransformer()

            def _get_all_agents(self):
                return self._agents

        space = MultiOutputSpace()
        assert isinstance(space.output_type, list), "output_type can be a list"
        assert space.output_type == [int, float, str], "List should contain specified types"

    def test_space_output_type_never_returns_none(self):
        """Space.output_type should never return None (blocks text output)."""
        space = GenericSpace()

        # This is critical - None would break PAI
        assert space.output_type is not None, "output_type must never be None!"
        assert space.output_type is str, "Default should be str, not None"


class TestPydanticModelOutputType:
    """Test that Pydantic models can be used as output types."""

    def test_custom_space_with_pydantic_model_output_type(self):
        """Custom Space can use Pydantic model as output_type."""

        class Report(BaseModel):
            """Test model for structured output."""

            title: str
            findings: List[str]

        class ModelOutputSpace(Space):
            """Test space that returns Pydantic models."""

            @property
            def output_type(self):
                return Report

            @property
            def active_agent(self):
                return self._agents[0] if self._agents else None

            def get_transformer(self):
                from chimera_core.threadprotocol.transformer import GenericTransformer

                return GenericTransformer()

            def _get_all_agents(self):
                return self._agents

        space = ModelOutputSpace()
        assert space.output_type is Report, "Space should support Pydantic model output_type"


class TestGenericSpaceDefaults:
    """Test that GenericSpace maintains backward compatibility."""

    def test_generic_space_uses_default_str(self):
        """GenericSpace should use default str output_type."""
        space = GenericSpace()

        # GenericSpace doesn't override output_type, so it should inherit default
        assert space.output_type is str, "GenericSpace should use default str output_type"

    def test_generic_space_has_no_custom_output_type_override(self):
        """Verify GenericSpace doesn't override output_type property."""
        from chimera_core.spaces.base import Space

        # Check that GenericSpace's output_type property comes from base Space
        assert GenericSpace.output_type == Space.output_type, (
            "GenericSpace should not override output_type property"
        )


class TestOutputTypeIntegrationWithAgent:
    """Test that Agent.run_stream() correctly reads output_type from space.

    Note: These are structural tests, not end-to-end execution tests.
    We verify the integration points are correct without mocking PAI.
    """

    def test_agent_code_reads_from_space_output_type(self):
        """Verify agent.py code structure reads ctx.state.active_space.output_type."""
        import inspect

        # Get the source code of Agent._run_pai_agent (where output_type is used)
        source = inspect.getsource(Agent._run_pai_agent)

        # Verify the code reads from ctx.state.active_space.output_type
        assert "ctx.state.active_space.output_type" in source, (
            "Agent._run_pai_agent should read output_type from space"
        )

        # Verify it doesn't use hardcoded [str, DeferredToolRequests]
        # (It should use the variable constructed from space.output_type)
        lines = source.split("\n")

        # Find lines with pai_agent.iter calls
        iter_calls = [line for line in lines if "pai_agent.iter(" in line or "output_type=" in line]

        # Check that output_type is passed as variable, not hardcoded list
        has_variable_usage = any("output_type=output_type" in line for line in iter_calls)
        assert has_variable_usage, (
            "Agent should use output_type variable (from space) in pai_agent.iter calls"
        )
