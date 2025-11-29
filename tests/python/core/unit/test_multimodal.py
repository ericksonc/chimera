"""Tests for multimodal (image/file upload) functionality."""

import pytest

from chimera_core.prompting import build_enhanced_user_message
from chimera_core.types import Attachment, UserInputMessage


# =============================================================================
# Attachment Model Tests
# =============================================================================


class TestAttachment:
    """Tests for the Attachment model."""

    def test_attachment_basic(self):
        """Test basic attachment creation."""
        attachment = Attachment(
            data_uri="data:image/jpeg;base64,/9j/4AAQ...",
            media_type="image/jpeg",
            filename="photo.jpg",
        )

        assert attachment.data_uri == "data:image/jpeg;base64,/9j/4AAQ..."
        assert attachment.media_type == "image/jpeg"
        assert attachment.filename == "photo.jpg"

    def test_attachment_without_filename(self):
        """Test attachment without optional filename."""
        attachment = Attachment(
            data_uri="data:image/png;base64,iVBORw0KGgo...",
            media_type="image/png",
        )

        assert attachment.data_uri.startswith("data:image/png;base64,")
        assert attachment.media_type == "image/png"
        assert attachment.filename is None


# =============================================================================
# UserInputMessage Tests
# =============================================================================


class TestUserInputMessage:
    """Tests for UserInputMessage with attachments."""

    def test_message_without_attachments(self):
        """Test message creation without attachments (backward compatible)."""
        message = UserInputMessage(
            content="Hello, world!",
        )

        assert message.kind == "message"
        assert message.content == "Hello, world!"
        assert message.attachments == []

    def test_message_with_attachments(self):
        """Test message with image attachments."""
        attachments = [
            Attachment(
                data_uri="data:image/jpeg;base64,/9j/4AAQ...",
                media_type="image/jpeg",
                filename="photo1.jpg",
            ),
            Attachment(
                data_uri="data:image/png;base64,iVBORw0KGgo...",
                media_type="image/png",
                filename="diagram.png",
            ),
        ]

        message = UserInputMessage(
            content="What's in these images?",
            attachments=attachments,
        )

        assert message.kind == "message"
        assert message.content == "What's in these images?"
        assert len(message.attachments) == 2
        assert message.attachments[0].media_type == "image/jpeg"
        assert message.attachments[1].media_type == "image/png"

    def test_message_serialization_with_attachments(self):
        """Test that message with attachments serializes to dict correctly."""
        message = UserInputMessage(
            content="Analyze this image",
            attachments=[
                Attachment(
                    data_uri="data:image/jpeg;base64,test123",
                    media_type="image/jpeg",
                    filename="test.jpg",
                )
            ],
            client_context={"cwd": "/home/user"},
        )

        data = message.model_dump()

        assert data["kind"] == "message"
        assert data["content"] == "Analyze this image"
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["data_uri"] == "data:image/jpeg;base64,test123"
        assert data["client_context"]["cwd"] == "/home/user"


# =============================================================================
# build_enhanced_user_message Tests
# =============================================================================


class TestBuildEnhancedUserMessage:
    """Tests for build_enhanced_user_message with multimodal support."""

    def test_plain_message_no_ambient_no_attachments(self):
        """Test plain message returns string directly."""
        result = build_enhanced_user_message(
            user_input="Hello, world!",
        )

        assert isinstance(result, str)
        assert result == "Hello, world!"

    def test_message_with_ambient_no_attachments(self):
        """Test message with ambient instructions returns enhanced string."""
        result = build_enhanced_user_message(
            user_input="What's the weather?",
            ambient_instructions=["You have access to a weather API."],
        )

        assert isinstance(result, str)
        assert "<ambient_context>" in result
        assert "You have access to a weather API." in result
        assert "<user_input>" in result
        assert "What's the weather?" in result

    def test_message_with_attachments_returns_list(self):
        """Test message with attachments returns list of content parts."""
        # Create a minimal valid base64 data URI (1x1 red PNG pixel)
        # This is a tiny valid PNG image
        png_data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        attachment = Attachment(
            data_uri=png_data_uri,
            media_type="image/png",
            filename="test.png",
        )

        result = build_enhanced_user_message(
            user_input="What's in this image?",
            attachments=[attachment],
        )

        # Should return a list when attachments present
        assert isinstance(result, list)
        assert len(result) == 2  # text + 1 attachment

        # First element is text
        assert result[0] == "What's in this image?"

        # Second element is BinaryContent from pydantic-ai
        from pydantic_ai.messages import BinaryContent

        assert isinstance(result[1], BinaryContent)

    def test_message_with_ambient_and_attachments(self):
        """Test message with both ambient instructions and attachments."""
        png_data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        attachment = Attachment(
            data_uri=png_data_uri,
            media_type="image/png",
        )

        result = build_enhanced_user_message(
            user_input="Analyze this diagram",
            ambient_instructions=["You are an image analysis expert."],
            attachments=[attachment],
        )

        # Should return list when attachments present
        assert isinstance(result, list)
        assert len(result) == 2  # enhanced text + 1 attachment

        # First element should have ambient context wrapping
        assert "<ambient_context>" in result[0]
        assert "image analysis expert" in result[0]
        assert "<user_input>" in result[0]
        assert "Analyze this diagram" in result[0]

    def test_multiple_attachments(self):
        """Test message with multiple attachments."""
        png_data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        jpeg_data_uri = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMCwsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="

        attachments = [
            Attachment(data_uri=png_data_uri, media_type="image/png", filename="a.png"),
            Attachment(
                data_uri=jpeg_data_uri, media_type="image/jpeg", filename="b.jpg"
            ),
        ]

        result = build_enhanced_user_message(
            user_input="Compare these images",
            attachments=attachments,
        )

        assert isinstance(result, list)
        assert len(result) == 3  # text + 2 attachments

        from pydantic_ai.messages import BinaryContent

        assert isinstance(result[0], str)
        assert isinstance(result[1], BinaryContent)
        assert isinstance(result[2], BinaryContent)

    def test_empty_attachments_list_returns_string(self):
        """Test that empty attachments list returns string (not list)."""
        result = build_enhanced_user_message(
            user_input="Hello",
            attachments=[],  # Empty list
        )

        # Empty list should be treated same as None
        assert isinstance(result, str)
        assert result == "Hello"
