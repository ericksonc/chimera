"""Tests for ThreadProtocol event validation."""

from chimera_core.threadprotocol.validation import EventOrderValidator, validate_event_ordering


class TestEventOrderValidator:
    """Tests for EventOrderValidator."""

    def test_valid_tool_call_sequence(self):
        """Validator passes for valid tool call → output sequence."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert result.success
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_valid_multiple_tool_calls(self):
        """Validator passes for multiple valid tool call sequences."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test1"},
            {"type": "tool-input-available", "toolCallId": "call_2", "toolName": "test2"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result1"},
            {"type": "tool-output-available", "toolCallId": "call_2", "output": "result2"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert result.success
        assert len(result.errors) == 0

    def test_valid_tool_call_with_error(self):
        """Validator passes for tool call → error sequence."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            {"type": "tool-output-error", "toolCallId": "call_1", "error": "Something failed"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert result.success
        assert len(result.errors) == 0

    def test_tool_output_before_call(self):
        """Validator detects tool output appearing before its call."""
        events = [
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "without preceding tool call" in result.errors[0]

    def test_duplicate_tool_call_id(self):
        """Validator detects duplicate tool call IDs."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test1"},
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test2"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "Duplicate tool call ID" in result.errors[0]

    def test_duplicate_tool_output(self):
        """Validator detects duplicate tool outputs for same call ID."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result1"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result2"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "Duplicate tool output" in result.errors[0]

    def test_tool_output_and_error_for_same_call(self):
        """Validator detects both output and error for same call ID."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
            {"type": "tool-output-error", "toolCallId": "call_1", "error": "Also errored?"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "Duplicate tool result" in result.errors[0]

    def test_missing_tool_call_id_in_call(self):
        """Validator detects missing toolCallId in tool-input-available."""
        events = [
            {"type": "tool-input-available", "toolName": "test"},  # Missing toolCallId
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "missing toolCallId" in result.errors[0]

    def test_missing_tool_call_id_in_output(self):
        """Validator detects missing toolCallId in tool-output-available."""
        events = [
            {"type": "tool-output-available", "output": "result"},  # Missing toolCallId
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 1
        assert "missing toolCallId" in result.errors[0]

    def test_orphaned_tool_call_warning_mode(self):
        """Validator warns about orphaned tool calls in non-strict mode."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            # No output or error for call_1
        ]

        validator = EventOrderValidator(strict=False)
        result = validator.validate(events)

        # Should succeed with warning
        assert result.success
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert "without results" in result.warnings[0]

    def test_orphaned_tool_call_strict_mode(self):
        """Validator errors on orphaned tool calls in strict mode."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            # No output or error for call_1
        ]

        validator = EventOrderValidator(strict=True)
        result = validator.validate(events)

        # Should fail with error
        assert not result.success
        assert len(result.errors) == 1
        assert "without results" in result.errors[0]

    def test_non_tool_events_ignored(self):
        """Validator ignores non-tool events."""
        events = [
            {"type": "data-user-message", "data": {"content": "Hello"}},
            {"type": "text-complete", "id": "text-1", "content": "Hi"},
            {"type": "data-agent-finish", "data": {"agentId": "agent-1"}},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        # Should pass (no tool events to validate)
        assert result.success
        assert len(result.errors) == 0

    def test_mixed_valid_and_invalid_events(self):
        """Validator detects multiple errors in mixed event stream."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test1"},
            {
                "type": "tool-output-available",
                "toolCallId": "call_2",
                "output": "orphan",
            },  # No call_2
            {
                "type": "tool-input-available",
                "toolCallId": "call_1",
                "toolName": "dup",
            },  # Duplicate
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
        ]

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert not result.success
        assert len(result.errors) == 2  # Output without call + duplicate call ID

    def test_empty_event_list(self):
        """Validator passes for empty event list."""
        events = []

        validator = EventOrderValidator()
        result = validator.validate(events)

        assert result.success
        assert len(result.errors) == 0


class TestValidateEventOrderingFunction:
    """Tests for validate_event_ordering convenience function."""

    def test_convenience_function_default(self):
        """Convenience function works with default parameters."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            {"type": "tool-output-available", "toolCallId": "call_1", "output": "result"},
        ]

        result = validate_event_ordering(events)

        assert result.success
        assert len(result.errors) == 0

    def test_convenience_function_strict(self):
        """Convenience function works with strict=True."""
        events = [
            {"type": "tool-input-available", "toolCallId": "call_1", "toolName": "test"},
            # Orphaned call
        ]

        result = validate_event_ordering(events, strict=True)

        assert not result.success
        assert len(result.errors) == 1


class TestValidationResultDataclass:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_success_property(self):
        """ValidationResult.success is True when valid and no errors."""
        from chimera_core.threadprotocol.validation import ValidationResult

        result = ValidationResult(valid=True, errors=[], warnings=["warning"])

        assert result.success

    def test_validation_result_failure_with_errors(self):
        """ValidationResult.success is False when errors present."""
        from chimera_core.threadprotocol.validation import ValidationResult

        result = ValidationResult(valid=False, errors=["error"], warnings=[])

        assert not result.success

    def test_validation_result_failure_when_invalid(self):
        """ValidationResult.success is False when valid=False."""
        from chimera_core.threadprotocol.validation import ValidationResult

        result = ValidationResult(valid=False, errors=[], warnings=[])

        assert not result.success
