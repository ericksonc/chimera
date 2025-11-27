"""Utilities for UI adapter infrastructure."""

from abc import ABC

from pydantic import BaseModel, ConfigDict


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase.

    Examples:
        >>> to_camel("tool_call_id")
        "toolCallId"
        >>> to_camel("provider_metadata")
        "providerMetadata"
    """
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class CamelBaseModel(BaseModel, ABC):
    """Base model with automatic camelCase aliasing for VSP compatibility.

    This enables writing Python code in snake_case while serializing to
    camelCase for VSP/JSON compatibility.

    Example:
        >>> class TextEvent(CamelBaseModel):
        ...     tool_call_id: str
        ...     provider_executed: bool | None = None

        >>> event = TextEvent(tool_call_id="call_123", provider_executed=True)
        >>> event.model_dump()
        {"toolCallId": "call_123", "providerExecuted": True}

        >>> # Can parse from both formats
        >>> TextEvent.model_validate({"toolCallId": "call_123"})  # camelCase ✅
        >>> TextEvent.model_validate({"tool_call_id": "call_123"})  # snake_case ✅
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # Accept both camelCase and snake_case
        extra="forbid",  # Reject unknown fields for safety
    )
