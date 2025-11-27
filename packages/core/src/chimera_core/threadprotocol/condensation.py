"""VSP event condensation logic for ThreadProtocol JSONL.

ThreadProtocol v0.0.7 condenses streaming deltas into complete events:
- text-start → text-delta* → text-end → text-complete
- reasoning-start → reasoning-delta* → reasoning-end → reasoning-complete
- tool-input-start → tool-input-delta* → tool-input-available → tool-input-available

This module handles the accumulation and merging logic.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TextAccumulator:
    """Accumulates text deltas into complete text event."""

    id: str
    text: str = ""
    provider_metadata: Optional[dict[str, Any]] = None

    def add_delta(self, delta: str) -> None:
        """Add a text delta."""
        self.text += delta

    def merge_metadata(self, metadata: Optional[dict[str, Any]]) -> None:
        """Merge provider metadata from start/end events."""
        if metadata:
            if self.provider_metadata is None:
                self.provider_metadata = {}
            self.provider_metadata.update(metadata)

    def to_complete_event(self) -> dict[str, Any]:
        """Convert to text-complete event for JSONL."""
        event: dict[str, Any] = {"type": "text-complete", "id": self.id, "content": self.text}
        if self.provider_metadata:
            event["providerMetadata"] = self.provider_metadata
        return event


@dataclass
class ReasoningAccumulator:
    """Accumulates reasoning deltas into complete reasoning event."""

    id: str
    text: str = ""
    provider_metadata: Optional[dict[str, Any]] = None

    def add_delta(self, delta: str) -> None:
        """Add a reasoning delta."""
        self.text += delta

    def merge_metadata(self, metadata: Optional[dict[str, Any]]) -> None:
        """Merge provider metadata from start/end events."""
        if metadata:
            if self.provider_metadata is None:
                self.provider_metadata = {}
            self.provider_metadata.update(metadata)

    def to_complete_event(self) -> dict[str, Any]:
        """Convert to reasoning-complete event for JSONL."""
        event: dict[str, Any] = {"type": "reasoning-complete", "id": self.id, "content": self.text}
        if self.provider_metadata:
            event["providerMetadata"] = self.provider_metadata
        return event


@dataclass
class ToolInputAccumulator:
    """Accumulates tool input metadata (we skip deltas, keep only final event)."""

    tool_call_id: str
    tool_name: Optional[str] = None
    dynamic: Optional[bool] = None
    title: Optional[str] = None
    provider_executed: Optional[bool] = None
    provider_metadata: Optional[dict[str, Any]] = None
    input: Optional[dict[str, Any]] = None

    def add_start_metadata(
        self, tool_name: str, dynamic: Optional[bool] = None, title: Optional[str] = None
    ) -> None:
        """Capture metadata from tool-input-start event."""
        self.tool_name = tool_name
        if dynamic is not None:
            self.dynamic = dynamic
        if title is not None:
            self.title = title

    def set_final_input(
        self,
        input: dict[str, Any],
        tool_name: str,
        provider_executed: Optional[bool] = None,
        provider_metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Set final input from tool-input-available event."""
        self.input = input
        if self.tool_name is None:
            self.tool_name = tool_name
        if provider_executed is not None:
            self.provider_executed = provider_executed
        if provider_metadata:
            self.provider_metadata = provider_metadata

    def to_complete_event(self) -> dict[str, Any]:
        """Convert to tool-input-available event for JSONL (keeps VSP type)."""
        if self.tool_name is None or self.input is None:
            raise ValueError(f"Tool input accumulator incomplete: tool_call_id={self.tool_call_id}")

        event: dict[str, Any] = {
            "type": "tool-input-available",
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "input": self.input,
        }

        # Add optional fields
        if self.provider_executed is not None:
            event["providerExecuted"] = self.provider_executed
        if self.dynamic is not None:
            event["dynamic"] = self.dynamic
        if self.title is not None:
            event["title"] = self.title
        if self.provider_metadata:
            event["providerMetadata"] = self.provider_metadata

        return event


@dataclass
class EventCondenser:
    """Condenses VSP streaming events into ThreadProtocol JSONL events.

    Maintains accumulators for text, reasoning, and tool inputs.
    Emits complete events when terminal events are received.
    """

    # Active accumulators
    text_parts: dict[str, TextAccumulator] = field(default_factory=dict)
    reasoning_parts: dict[str, ReasoningAccumulator] = field(default_factory=dict)
    tool_inputs: dict[str, ToolInputAccumulator] = field(default_factory=dict)

    def process_event(self, event: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Process a VSP event and return condensed event if ready.

        Args:
            event: VSP streaming event

        Returns:
            Condensed event ready for JSONL, or None if accumulating
        """
        event_type = event.get("type")

        # Text content condensation
        if event_type == "text-start":
            part_id = event["id"]
            self.text_parts[part_id] = TextAccumulator(
                id=part_id, provider_metadata=event.get("providerMetadata")
            )
            return None

        elif event_type == "text-delta":
            part_id = event["id"]
            if part_id in self.text_parts:
                self.text_parts[part_id].add_delta(event["delta"])
            return None

        elif event_type == "text-end":
            part_id = event["id"]
            if part_id in self.text_parts:
                accumulator = self.text_parts.pop(part_id)
                accumulator.merge_metadata(event.get("providerMetadata"))
                return accumulator.to_complete_event()
            return None

        # Reasoning content condensation
        elif event_type == "reasoning-start":
            part_id = event["id"]
            self.reasoning_parts[part_id] = ReasoningAccumulator(
                id=part_id, provider_metadata=event.get("providerMetadata")
            )
            return None

        elif event_type == "reasoning-delta":
            part_id = event["id"]
            if part_id in self.reasoning_parts:
                self.reasoning_parts[part_id].add_delta(event["delta"])
            return None

        elif event_type == "reasoning-end":
            part_id = event["id"]
            if part_id in self.reasoning_parts:
                accumulator = self.reasoning_parts.pop(part_id)
                accumulator.merge_metadata(event.get("providerMetadata"))
                return accumulator.to_complete_event()
            return None

        # Tool input condensation
        elif event_type == "tool-input-start":
            tool_call_id = event["toolCallId"]
            self.tool_inputs[tool_call_id] = ToolInputAccumulator(tool_call_id=tool_call_id)
            self.tool_inputs[tool_call_id].add_start_metadata(
                tool_name=event["toolName"], dynamic=event.get("dynamic"), title=event.get("title")
            )
            return None

        elif event_type == "tool-input-delta":
            # Skip input deltas - we only care about final parsed input
            return None

        elif event_type == "tool-input-available":
            tool_call_id = event["toolCallId"]

            # Get or create accumulator
            if tool_call_id not in self.tool_inputs:
                self.tool_inputs[tool_call_id] = ToolInputAccumulator(tool_call_id=tool_call_id)

            accumulator = self.tool_inputs.pop(tool_call_id)
            accumulator.set_final_input(
                input=event["input"],
                tool_name=event["toolName"],
                provider_executed=event.get("providerExecuted"),
                provider_metadata=event.get("providerMetadata"),
            )
            return accumulator.to_complete_event()

        # Events NOT saved to JSONL
        elif event_type in ("start", "finish", "abort"):
            return None

        # Transient custom events
        elif event_type.startswith("data-") and event.get("transient"):
            return None

        # All other events pass through unchanged
        else:
            return event

    def reset(self) -> None:
        """Clear all accumulators (e.g., between messages)."""
        self.text_parts.clear()
        self.reasoning_parts.clear()
        self.tool_inputs.clear()
