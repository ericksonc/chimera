"""Event assertion helpers for testing VSP and ThreadProtocol event emission.

These utilities make it easy to verify event sequences, structure, and
the critical boundary vs delta distinction for VSP events.
"""

from typing import Any


def assert_event_sequence(events: list[tuple[bool, dict]], expected_types: list[str]):
    """Assert that events match expected type sequence.

    Args:
        events: List of (include_thread_id, event_dict) tuples from mock_thread_deps
        expected_types: List of expected event types in order

    Example:
        assert_event_sequence(deps.emitted_vsp, [
            "start",
            "text-start",
            "text-delta",
            "text-end",
            "finish"
        ])
    """
    actual_types = [event["type"] for _, event in events]
    assert actual_types == expected_types, (
        f"Event sequence mismatch.\nExpected: {expected_types}\nActual:   {actual_types}"
    )


def assert_boundary_event(event: tuple[bool, dict], expected_type: str):
    """Assert event is a boundary event (includes threadId).

    Boundary events mark state transitions and always include threadId:
    - start, finish
    - text-start, text-end
    - tool-input-start, tool-input-available, tool-output-available
    - reasoning-start, reasoning-end
    - agent-turn-start, agent-turn-end
    - user-turn-start, user-turn-end

    Args:
        event: (include_thread_id, event_dict) tuple
        expected_type: Expected event type

    Example:
        first_event = deps.emitted_vsp[0]
        assert_boundary_event(first_event, "start")
    """
    include_thread_id, evt = event
    assert include_thread_id, (
        f"Boundary event '{expected_type}' must include threadId.\nEvent: {evt}"
    )
    assert evt["type"] == expected_type, (
        f"Expected boundary event type '{expected_type}', got '{evt['type']}'"
    )


def assert_delta_event(event: tuple[bool, dict], expected_type: str):
    """Assert event is a delta event (NO threadId).

    Delta events stream incremental content and never include threadId:
    - text-delta
    - tool-input-delta
    - reasoning-delta

    Args:
        event: (include_thread_id, event_dict) tuple
        expected_type: Expected event type

    Example:
        delta_event = deps.emitted_vsp[2]
        assert_delta_event(delta_event, "text-delta")
    """
    include_thread_id, evt = event
    assert not include_thread_id, (
        f"Delta event '{expected_type}' must NOT include threadId.\nEvent: {evt}"
    )
    assert evt["type"] == expected_type, (
        f"Expected delta event type '{expected_type}', got '{evt['type']}'"
    )


def assert_event_type(event: tuple[bool, dict], expected_type: str):
    """Assert event has expected type (doesn't check threadId).

    Use this when you don't care about boundary vs delta distinction.

    Args:
        event: (include_thread_id, event_dict) tuple
        expected_type: Expected event type
    """
    _, evt = event
    assert evt["type"] == expected_type, (
        f"Expected event type '{expected_type}', got '{evt['type']}'"
    )


def assert_event_field(event: tuple[bool, dict], field: str, expected_value: Any = None):
    """Assert event has field, optionally with specific value.

    Args:
        event: (include_thread_id, event_dict) tuple
        field: Field name to check
        expected_value: If provided, assert field equals this value

    Example:
        assert_event_field(event, "messageId")  # Just check exists
        assert_event_field(event, "agentId", "test-agent-001")  # Check value
    """
    _, evt = event
    assert field in evt, f"Event missing expected field '{field}'.\nEvent: {evt}"
    if expected_value is not None:
        assert evt[field] == expected_value, (
            f"Event field '{field}' has wrong value.\n"
            f"Expected: {expected_value}\n"
            f"Actual: {evt[field]}"
        )


def find_events_by_type(
    events: list[tuple[bool, dict]], event_type: str
) -> list[tuple[bool, dict]]:
    """Find all events with given type.

    Args:
        events: List of (include_thread_id, event_dict) tuples
        event_type: Event type to find

    Returns:
        List of matching events

    Example:
        text_deltas = find_events_by_type(deps.emitted_vsp, "text-delta")
        assert len(text_deltas) > 0
    """
    return [event for event in events if event[1]["type"] == event_type]


def assert_event_count(events: list[tuple[bool, dict]], event_type: str, expected_count: int):
    """Assert specific number of events with given type.

    Args:
        events: List of (include_thread_id, event_dict) tuples
        event_type: Event type to count
        expected_count: Expected number of events

    Example:
        assert_event_count(deps.emitted_vsp, "text-delta", 5)
    """
    matching = find_events_by_type(events, event_type)
    actual_count = len(matching)
    assert actual_count == expected_count, (
        f"Expected {expected_count} '{event_type}' events, got {actual_count}"
    )


def assert_threadprotocol_events(events: list[dict], expected_types: list[str]):
    """Assert ThreadProtocol events match expected type sequence.

    Similar to assert_event_sequence but for ThreadProtocol events
    (which don't have the include_thread_id tuple wrapper).

    Args:
        events: List of event dicts from deps.emitted_threadprotocol
        expected_types: List of expected event types in order

    Example:
        assert_threadprotocol_events(deps.emitted_threadprotocol, [
            "tool-input-available",
            "tool-output-available"
        ])
    """
    actual_types = [event["type"] for event in events]
    assert actual_types == expected_types, (
        f"ThreadProtocol event sequence mismatch.\n"
        f"Expected: {expected_types}\n"
        f"Actual:   {actual_types}"
    )
