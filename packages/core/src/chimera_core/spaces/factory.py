"""SpaceFactory - Centralized space creation from BlueprintProtocol.

This factory encapsulates the logic for creating Space instances from
BlueprintProtocol configuration, ensuring the API layer doesn't need
to know about DefaultSpaceConfig vs ReferencedSpaceConfig distinctions.

Architectural Principle:
- API layer should not contain core business logic
- Space creation belongs in core layer, not API layer
- Single Responsibility: Factory handles only space instantiation
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chimera_core.spaces.base import Space
    from chimera_core.threadprotocol.blueprint import SpaceConfig


class SpaceFactory:
    """Factory for creating Space instances from BlueprintProtocol configuration.

    This centralizes the logic that was previously scattered in api/stream_handler.py,
    providing a clean interface for space creation that the API layer can consume.
    """

    @staticmethod
    def from_blueprint_config(space_config: "SpaceConfig") -> "Space":
        """Create Space from BlueprintProtocol configuration.

        Handles both DefaultSpaceConfig and ReferencedSpaceConfig:
        - DefaultSpaceConfig → Creates GenericSpace
        - ReferencedSpaceConfig → Dynamically loads specified Space class

        The factory determines which Space class to instantiate, then
        delegates to that class's from_blueprint_config() method for
        actual construction (agent resolution, widget loading, etc.).

        Args:
            space_config: SpaceConfig from Blueprint (DefaultSpaceConfig | ReferencedSpaceConfig)

        Returns:
            Fully constructed Space instance with resolved agents

        Raises:
            ValueError: If space_config type is unknown or Space class cannot be loaded

        Example:
            >>> from chimera_core.threadprotocol.blueprint import Blueprint
            >>> blueprint = Blueprint.from_event(thread_jsonl[0])
            >>> space = SpaceFactory.from_blueprint_config(blueprint.space)
        """
        from chimera_core.spaces.base import Space
        from chimera_core.threadprotocol.blueprint import DefaultSpaceConfig, ReferencedSpaceConfig

        # Determine which Space class to instantiate
        if isinstance(space_config, DefaultSpaceConfig):
            # Default space is GenericSpace (minimal orchestration)
            class_name = "core.spaces.GenericSpace"
        elif isinstance(space_config, ReferencedSpaceConfig):
            # Custom space - use class_name from config
            class_name = space_config.class_name
        else:
            raise ValueError(
                f"Unknown space config type: {type(space_config)}. "
                f"Expected DefaultSpaceConfig or ReferencedSpaceConfig."
            )

        # Dynamically load the Space class
        # Space.load_space_class() handles validation and error messages
        space_class = Space.load_space_class(class_name)

        # Delegate to the Space class's from_blueprint_config() method
        # This handles agent resolution (inline/referenced), widget loading, etc.
        return space_class.from_blueprint_config(space_config)
