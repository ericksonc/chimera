"""Base classes for VSP (Vercel AI SDK Data Stream Protocol) event types.

This module provides utilities for automatic camelCase field aliasing,
ensuring VSP compatibility without manual Field(alias=...) specifications.

Example:
    class TextStartEvent(VSPBaseModel):
        type: Literal['text-start']
        id: str
        provider_metadata: dict | None = None
        # Automatically serializes as: {"type":"text-start","id":"...","providerMetadata":{...}}
"""

from abc import ABC

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class VSPBaseModel(BaseModel, ABC):
    """Base model for VSP event types with automatic camelCase aliases.

    This base class provides:
    - Automatic camelCase field name generation (snake_case → camelCase)
    - Accepts both formats during parsing (populate_by_name=True)
    - Rejects unknown fields (extra='forbid')

    Inherit from this when defining VSP event type models to ensure
    consistent field naming without manual alias specifications.

    Example:
        ```python
        class ToolInputAvailableEvent(VSPBaseModel):
            type: Literal['tool-input-available']
            tool_call_id: str  # Becomes "toolCallId" in JSON
            tool_name: str     # Becomes "toolName" in JSON
            input: dict
            provider_executed: bool | None = None  # Becomes "providerExecuted"

        # Usage:
        event = ToolInputAvailableEvent(
            type='tool-input-available',
            tool_call_id='call-123',
            tool_name='weather',
            input={'city': 'NYC'}
        )

        # Serializes to:
        # {"type":"tool-input-available","toolCallId":"call-123",
        #  "toolName":"weather","input":{"city":"NYC"}}
        ```
    """

    model_config = ConfigDict(
        # Automatically generate camelCase aliases from snake_case field names
        alias_generator=to_camel,
        # Accept both snake_case and camelCase during parsing
        # Useful for accepting data from various sources
        populate_by_name=True,
        # Reject unknown fields to catch errors early
        # VSP has strict schemas, extra fields should fail validation
        extra="forbid",
    )
