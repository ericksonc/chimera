"""Prompt construction utilities for Chimera.

This module provides utilities for constructing enhanced user messages that
separate ambient context from actual user input using <ambient_context> tags.

Architecture Decision (2025-11-11):
- Agent base_prompt (persona) goes in LLM system prompt via PAI's `instructions`
- Dynamic instructions from widgets/spaces go in ENHANCED USER MESSAGE
- Clear demarcation between what user typed vs. ambient context
- XML tags only appear when ambient context is actually present
"""

from typing import List


def build_enhanced_user_message(
    user_input: str, ambient_instructions: List[str] | None = None
) -> str:
    """Build an enhanced user message with clear demarcation.

    This constructs a message that clearly separates:
    1. System-provided ambient context/instructions (from widgets/spaces)
    2. What the user actually typed

    When no ambient instructions are present, returns the user input directly
    without any XML wrapping.

    Args:
        user_input: The actual message the user typed
        ambient_instructions: Optional list of dynamic instructions from widgets/spaces

    Returns:
        Enhanced message string with XML demarcation if ambient context exists,
        or plain user input if no ambient context.

    Example with ambient context:
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

    Example without ambient context:
        >>> build_enhanced_user_message(
        ...     user_input="What's the weather?",
        ...     ambient_instructions=None
        ... )
        What's the weather?
    """
    # If no ambient instructions, return user input directly (no wrapping)
    if not ambient_instructions:
        return user_input

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

    return "\n".join(parts)
