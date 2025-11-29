"""Prompt construction utilities for Chimera.

This module provides utilities for constructing enhanced user messages that
separate ambient context from actual user input using <ambient_context> tags.

Architecture Decision (2025-11-11):
- Agent base_prompt (persona) goes in LLM system prompt via PAI's `instructions`
- Dynamic instructions from widgets/spaces go in ENHANCED USER MESSAGE
- Clear demarcation between what user typed vs. ambient context
- XML tags only appear when ambient context is actually present

Multimodal Support (2025-11):
- Attachments (images, files) are converted to Pydantic AI BinaryContent
- Returns list[str | BinaryContent] when attachments present
- Pydantic AI handles multimodal content natively via .iter()
"""

from typing import List, Sequence, Union

from pydantic_ai.messages import BinaryContent, UserContent

from chimera_core.types import Attachment


def build_enhanced_user_message(
    user_input: str,
    ambient_instructions: List[str] | None = None,
    attachments: List[Attachment] | None = None,
) -> str | Sequence[UserContent]:
    """Build an enhanced user message with clear demarcation.

    This constructs a message that clearly separates:
    1. System-provided ambient context/instructions (from widgets/spaces)
    2. What the user actually typed
    3. Any attached files/images (multimodal content)

    When no ambient instructions are present and no attachments, returns the
    user input directly without any XML wrapping.

    Args:
        user_input: The actual message the user typed
        ambient_instructions: Optional list of dynamic instructions from widgets/spaces
        attachments: Optional list of file/image attachments for multimodal input

    Returns:
        - str: When no attachments present (with or without ambient context)
        - Sequence[UserContent]: When attachments present (text + BinaryContent items)

    Example with ambient context (no attachments):
        >>> build_enhanced_user_message(
        ...     user_input="What's the weather?",
        ...     ambient_instructions=["You have access to a weather API"]
        ... )
        <ambient_context>
        You have access to a weather API
        </ambient_context>

        <user_input>
        What's the weather?
        </user_input>

    Example without ambient context (no attachments):
        >>> build_enhanced_user_message(
        ...     user_input="What's the weather?",
        ...     ambient_instructions=None
        ... )
        What's the weather?

    Example with attachments:
        >>> build_enhanced_user_message(
        ...     user_input="What's in this image?",
        ...     attachments=[Attachment(data_uri="data:image/jpeg;base64,...", media_type="image/jpeg")]
        ... )
        ["What's in this image?", BinaryContent(...)]
    """
    # Build the text part of the message
    if not ambient_instructions:
        text_content = user_input
    else:
        parts = []
        # Add ambient instructions
        parts.append("<ambient_context>")
        parts.extend(ambient_instructions)
        parts.append("</ambient_context>")

        # Add user input section
        parts.append("")  # Blank line for readability
        parts.append("<user_input>")
        parts.append(user_input)
        parts.append("</user_input>")

        text_content = "\n".join(parts)

    # If no attachments, return plain string (backward compatible)
    if not attachments:
        return text_content

    # Build multimodal content: text first, then attachments
    content_parts: List[Union[str, BinaryContent]] = [text_content]

    for attachment in attachments:
        # Convert data URI to BinaryContent using pydantic-ai's helper
        binary_content = BinaryContent.from_data_uri(attachment.data_uri)
        content_parts.append(binary_content)

    return content_parts
