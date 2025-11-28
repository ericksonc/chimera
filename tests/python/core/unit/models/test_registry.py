"""Tests for Model Registry data models and service."""

from datetime import datetime, timezone

import pytest

from chimera_core.models.registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    Provider,
)


class TestModelCapabilities:
    """Tests for ModelCapabilities model."""

    def test_default_values(self):
        """Default capabilities should be text-only."""
        caps = ModelCapabilities()
        assert caps.text_input is True
        assert caps.text_output is True
        assert caps.image_input is False
        assert caps.function_calling is False
        assert caps.streaming is True

    def test_vision_model(self):
        """Vision model should have image_input enabled."""
        caps = ModelCapabilities(image_input=True)
        assert caps.image_input is True
        assert caps.text_input is True

    def test_multimodal_model(self):
        """Multimodal model with all inputs."""
        caps = ModelCapabilities(
            image_input=True,
            audio_input=True,
            video_input=True,
            function_calling=True,
        )
        assert caps.image_input is True
        assert caps.audio_input is True
        assert caps.video_input is True
        assert caps.function_calling is True


class TestModelPricing:
    """Tests for ModelPricing model."""

    def test_basic_pricing(self):
        """Basic input/output pricing."""
        pricing = ModelPricing(
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
        )
        assert pricing.input_cost_per_million == 3.0
        assert pricing.output_cost_per_million == 15.0
        assert pricing.image_cost_per_image is None

    def test_pricing_with_images(self):
        """Pricing with image costs."""
        pricing = ModelPricing(
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
            image_cost_per_image=0.0025,
        )
        assert pricing.image_cost_per_image == 0.0025

    def test_negative_cost_rejected(self):
        """Negative costs should be rejected."""
        with pytest.raises(ValueError):
            ModelPricing(
                input_cost_per_million=-1.0,
                output_cost_per_million=15.0,
            )


class TestModelMetadata:
    """Tests for ModelMetadata model."""

    def test_basic_model(self):
        """Create a basic model metadata."""
        model = ModelMetadata(
            id="openrouter:anthropic/claude-3.5-sonnet",
            provider=Provider.OPENROUTER,
            provider_model_id="anthropic/claude-3.5-sonnet",
            display_name="Claude 3.5 Sonnet",
            max_context_window=200000,
        )
        assert model.id == "openrouter:anthropic/claude-3.5-sonnet"
        assert model.provider == Provider.OPENROUTER
        assert model.display_name == "Claude 3.5 Sonnet"
        assert model.is_available is True

    def test_full_id_property(self):
        """full_id should return model.id (kept for API compatibility)."""
        model = ModelMetadata(
            id="openrouter:openai/gpt-4o",
            provider=Provider.OPENROUTER,
            provider_model_id="openai/gpt-4o",
            display_name="GPT-4o",
            max_context_window=128000,
        )
        assert model.full_id == "openrouter:openai/gpt-4o"
        assert model.full_id == model.id

    def test_supports_method(self):
        """supports() should check capability flags."""
        model = ModelMetadata(
            id="test:model",
            provider=Provider.OPENROUTER,
            provider_model_id="test/model",
            display_name="Test Model",
            max_context_window=8192,
            capabilities=ModelCapabilities(
                image_input=True,
                function_calling=True,
            ),
        )
        assert model.supports("image_input") is True
        assert model.supports("function_calling") is True
        assert model.supports("audio_input") is False
        assert model.supports("nonexistent") is False

    def test_model_with_pricing(self):
        """Model with full pricing information."""
        model = ModelMetadata(
            id="openrouter:anthropic/claude-3.5-sonnet",
            provider=Provider.OPENROUTER,
            provider_model_id="anthropic/claude-3.5-sonnet",
            display_name="Claude 3.5 Sonnet",
            max_context_window=200000,
            max_output_tokens=8192,
            pricing=ModelPricing(
                input_cost_per_million=3.0,
                output_cost_per_million=15.0,
            ),
        )
        assert model.pricing is not None
        assert model.pricing.input_cost_per_million == 3.0

    def test_last_updated_default(self):
        """last_updated should default to now."""
        before = datetime.now(timezone.utc)
        model = ModelMetadata(
            id="test:model",
            provider=Provider.GEMINI,
            provider_model_id="gemini-2.0-flash",
            display_name="Gemini 2.0 Flash",
            max_context_window=1000000,
        )
        after = datetime.now(timezone.utc)
        assert before <= model.last_updated <= after


class TestProvider:
    """Tests for Provider enum."""

    def test_provider_values(self):
        """Provider enum should have expected values."""
        assert Provider.OPENROUTER.value == "openrouter"
        assert Provider.GEMINI.value == "gemini"
        assert Provider.KIMI.value == "kimi"

    def test_provider_from_string(self):
        """Should create Provider from string."""
        assert Provider("openrouter") == Provider.OPENROUTER
        assert Provider("gemini") == Provider.GEMINI

    def test_invalid_provider(self):
        """Invalid provider string should raise."""
        with pytest.raises(ValueError):
            Provider("invalid")
