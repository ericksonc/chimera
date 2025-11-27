"""Model registry data models.

Defines the schema for model metadata, capabilities, and pricing information
used by the ModelRegistryService for multi-provider model tracking.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Provider(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    KIMI = "kimi"


class ModelCapabilities(BaseModel):
    """Model capability flags.

    Explicit boolean flags for each capability type.
    Avoids inference from provider-specific formats.
    """

    text_input: bool = Field(default=True, description="Accepts text input")
    image_input: bool = Field(default=False, description="Accepts image input (vision)")
    audio_input: bool = Field(default=False, description="Accepts audio input")
    video_input: bool = Field(default=False, description="Accepts video input")
    text_output: bool = Field(default=True, description="Generates text output")
    image_output: bool = Field(default=False, description="Generates image output")
    audio_output: bool = Field(default=False, description="Generates audio output")
    function_calling: bool = Field(default=False, description="Supports function/tool calling")
    streaming: bool = Field(default=True, description="Supports streaming responses")
    json_mode: bool = Field(default=False, description="Supports structured JSON output")
    system_prompt: bool = Field(default=True, description="Supports system prompts")


class ModelPricing(BaseModel):
    """Model pricing information in USD.

    All costs are per million tokens unless otherwise specified.
    """

    input_cost_per_million: float = Field(..., description="Cost per 1M input tokens in USD", ge=0)
    output_cost_per_million: float = Field(
        ..., description="Cost per 1M output tokens in USD", ge=0
    )
    image_cost_per_image: Optional[float] = Field(
        default=None, description="Cost per image input in USD"
    )
    cached_input_cost_per_million: Optional[float] = Field(
        default=None, description="Cost per 1M cached input tokens in USD"
    )


class ModelMetadata(BaseModel):
    """Complete model metadata.

    Aggregates provider information, capabilities, pricing, and context limits.
    """

    id: str = Field(
        ...,
        description="Unique model identifier (e.g., 'openrouter:anthropic/claude-3.5-sonnet')",
    )
    provider: Provider = Field(..., description="Provider enum value")
    provider_model_id: str = Field(
        ...,
        description="Model ID as used with the provider API (e.g., 'anthropic/claude-3.5-sonnet')",
    )
    display_name: str = Field(..., description="Human-readable model name")
    description: Optional[str] = Field(default=None, description="Model description")
    capabilities: ModelCapabilities = Field(
        default_factory=ModelCapabilities, description="Model capabilities"
    )
    pricing: Optional[ModelPricing] = Field(
        default=None, description="Pricing information (None if free/unknown)"
    )
    max_context_window: int = Field(..., description="Maximum context window in tokens", gt=0)
    max_output_tokens: Optional[int] = Field(
        default=None, description="Maximum output tokens (None if unlimited/unknown)"
    )
    is_available: bool = Field(default=True, description="Whether the model is currently available")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this metadata was last updated",
    )

    @property
    def full_id(self) -> str:
        """Return the full model ID with provider prefix.

        Note: This is equivalent to self.id since adapters already set id
        in the format 'provider:model_id'. Kept for API compatibility.
        """
        return self.id

    def supports(self, capability: str) -> bool:
        """Check if model supports a specific capability.

        Args:
            capability: Capability name (e.g., 'image_input', 'function_calling')

        Returns:
            True if capability is supported, False otherwise
        """
        if hasattr(self.capabilities, capability):
            return bool(getattr(self.capabilities, capability))
        return False


class ModelListResponse(BaseModel):
    """API response for model list endpoint."""

    models: list[ModelMetadata] = Field(default_factory=list)
    total: int = Field(default=0)
    cached_at: Optional[datetime] = Field(default=None)


class ModelsByCapabilityResponse(BaseModel):
    """API response for models grouped by capability."""

    capability: str
    models: list[ModelMetadata] = Field(default_factory=list)
    total: int = Field(default=0)
