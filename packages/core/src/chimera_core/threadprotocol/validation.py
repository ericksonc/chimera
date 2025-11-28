"""ThreadProtocol event validation.

Validates event ordering, consistency, and referential integrity.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of event validation."""

    valid: bool
    errors: List[str]
    warnings: List[str]

    @property
    def success(self) -> bool:
        """Returns True if validation passed with no errors."""
        return self.valid and len(self.errors) == 0


class EventOrderValidator:
    """Validates event ordering and referential integrity.

    Checks for:
    - Tool calls appear before their outputs
    - No duplicate tool call IDs
    - All tool outputs have corresponding tool calls
    - No orphaned tool calls (calls without results are allowed, but logged)
    """

    def __init__(self, strict: bool = False):
        """Initialize validator.

        Args:
            strict: If True, orphaned tool calls are errors. If False, they're warnings.
        """
        self.strict = strict

    def validate(self, events: List[Dict[str, Any]]) -> ValidationResult:
        """Validate event ordering and consistency.

        Args:
            events: List of ThreadProtocol events

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []

        # Track tool calls and their states
        tool_calls: dict[str, int] = {}  # tool_call_id -> event index
        tool_results = set()  # Set of tool_call_ids that have results

        for idx, event in enumerate(events):
            event_type = event.get("type")

            # Check tool-input-available events
            if event_type == "tool-input-available":
                tool_call_id = event.get("toolCallId")

                if not tool_call_id:
                    errors.append(f"Event {idx}: tool-input-available missing toolCallId")
                    continue

                if tool_call_id in tool_calls:
                    errors.append(
                        f"Event {idx}: Duplicate tool call ID '{tool_call_id}' "
                        f"(first seen at event {tool_calls[tool_call_id]})"
                    )
                else:
                    tool_calls[tool_call_id] = idx

            # Check tool-output-available events
            elif event_type == "tool-output-available":
                tool_call_id = event.get("toolCallId")

                if not tool_call_id:
                    errors.append(f"Event {idx}: tool-output-available missing toolCallId")
                    continue

                if tool_call_id not in tool_calls:
                    errors.append(
                        f"Event {idx}: Tool output for '{tool_call_id}' without preceding tool call"
                    )
                elif tool_call_id in tool_results:
                    errors.append(f"Event {idx}: Duplicate tool output for '{tool_call_id}'")
                else:
                    tool_results.add(tool_call_id)

            # Check tool-output-error events
            elif event_type == "tool-output-error":
                tool_call_id = event.get("toolCallId")

                if not tool_call_id:
                    errors.append(f"Event {idx}: tool-output-error missing toolCallId")
                    continue

                if tool_call_id not in tool_calls:
                    errors.append(
                        f"Event {idx}: Tool error for '{tool_call_id}' without preceding tool call"
                    )
                elif tool_call_id in tool_results:
                    errors.append(
                        f"Event {idx}: Duplicate tool result for '{tool_call_id}' "
                        f"(already has output or error)"
                    )
                else:
                    tool_results.add(tool_call_id)

        # Check for orphaned tool calls (calls without results)
        orphaned = set(tool_calls.keys()) - tool_results
        if orphaned:
            message = (
                f"Found {len(orphaned)} tool call(s) without results: {', '.join(sorted(orphaned))}"
            )
            if self.strict:
                errors.append(message)
            else:
                warnings.append(message)
                logger.debug(f"Orphaned tool calls (non-fatal): {orphaned}")

        # Determine validity
        valid = len(errors) == 0

        return ValidationResult(valid=valid, errors=errors, warnings=warnings)


def validate_event_ordering(events: List[Dict[str, Any]], strict: bool = False) -> ValidationResult:
    """Convenience function to validate event ordering.

    Args:
        events: List of ThreadProtocol events
        strict: If True, orphaned tool calls are errors

    Returns:
        ValidationResult
    """
    validator = EventOrderValidator(strict=strict)
    return validator.validate(events)
