"""ThreadProtocol v0.0.5 handler for CLI.

Handles building ThreadProtocol JSONL from VSP events and persisting threads.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4


class DeltaAccumulator:
    """Accumulates delta events into complete ThreadProtocol events."""

    def __init__(self):
        """Initialize accumulator."""
        self.accumulators: Dict[str, Dict[str, Any]] = {}  # part_id -> event data

    def start_part(self, part_id: str, event_type: str, metadata: Dict[str, Any]):
        """Start accumulating a new part.

        Args:
            part_id: Unique identifier for this part
            event_type: Type of event (text, tool_call, thinking)
            metadata: Additional metadata (agent_id, etc.)
        """
        self.accumulators[part_id] = {
            "event_type": event_type,
            "content": "",
            "metadata": metadata,
            "part_id": part_id
        }

    def add_delta(self, part_id: str, delta: str):
        """Add delta content to accumulator.

        Args:
            part_id: Part identifier
            delta: Content delta to append
        """
        if part_id in self.accumulators:
            self.accumulators[part_id]["content"] += delta

    def finalize_part(self, part_id: str) -> Optional[Dict[str, Any]]:
        """Finalize part and return ThreadProtocol event.

        Args:
            part_id: Part identifier

        Returns:
            ThreadProtocol event dict or None if part not found
        """
        if part_id not in self.accumulators:
            return None

        acc = self.accumulators.pop(part_id)

        # Build ThreadProtocol event
        event = {
            "event_type": acc["event_type"],
            "content": acc["content"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Add metadata fields
        event.update(acc["metadata"])

        return event


class ThreadProtocolBuilder:
    """Builds ThreadProtocol JSONL from VSP events."""

    def __init__(self, blueprint_event: Dict[str, Any]):
        """Initialize builder with blueprint.

        Args:
            blueprint_event: BlueprintProtocol event (first line of JSONL)
        """
        self.events: List[Dict[str, Any]] = [blueprint_event]
        self.accumulator = DeltaAccumulator()
        self.current_agent_id: Optional[str] = None

    def process_vsp_event(self, vsp_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a VSP event and return ThreadProtocol event if complete.

        Args:
            vsp_event: VSP event from SSE stream

        Returns:
            ThreadProtocol event if one should be written, None otherwise
        """
        event_type = vsp_event.get("type")

        # Handle turn boundaries (pass through directly)
        if event_type in ["user-turn-start", "user-turn-end", "agent-turn-start", "agent-turn-end"]:
            return self._handle_turn_boundary(vsp_event)

        # Handle state mutations (pass through unchanged)
        if event_type == "data-app-chimera":
            return self._handle_state_mutation(vsp_event)

        # Handle delta accumulation
        if event_type == "text-start":
            return self._handle_text_start(vsp_event)
        elif event_type == "text-delta":
            return self._handle_text_delta(vsp_event)
        elif event_type == "text-end":
            return self._handle_text_end(vsp_event)

        elif event_type == "reasoning-start":
            return self._handle_reasoning_start(vsp_event)
        elif event_type == "reasoning-delta":
            return self._handle_reasoning_delta(vsp_event)
        elif event_type == "reasoning-end":
            return self._handle_reasoning_end(vsp_event)

        elif event_type == "tool-input-start":
            return self._handle_tool_input_start(vsp_event)
        elif event_type == "tool-input-delta":
            return self._handle_tool_input_delta(vsp_event)
        elif event_type == "tool-input-available":
            return self._handle_tool_input_available(vsp_event)

        elif event_type == "tool-output-available":
            return self._handle_tool_output(vsp_event)

        # Step boundaries
        elif event_type in ["start-step", "finish-step"]:
            return self._handle_step_boundary(vsp_event)

        # Errors
        elif event_type == "error":
            return self._handle_error(vsp_event)

        return None

    def _handle_turn_boundary(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle turn boundary events."""
        event_type = vsp_event["type"].replace("-", "_")

        event = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Track current agent for delta events
        if event_type == "agent_turn_start":
            self.current_agent_id = vsp_event.get("agentId")
            event["agent_id"] = self.current_agent_id
            if "agentName" in vsp_event:
                event["agent_name"] = vsp_event["agentName"]
        elif event_type == "agent_turn_end":
            event["agent_id"] = vsp_event.get("agentId", self.current_agent_id)
            event["completion_status"] = vsp_event.get("completionStatus", "complete")

        return event

    def _handle_state_mutation(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle state mutation events (pass through)."""
        # State mutations already in correct format
        event = dict(vsp_event)
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        return event

    def _handle_text_start(self, vsp_event: Dict[str, Any]) -> None:
        """Handle text-start event."""
        part_id = vsp_event.get("id")
        metadata = {"agent_id": self.current_agent_id}
        self.accumulator.start_part(part_id, "text", metadata)
        return None

    def _handle_text_delta(self, vsp_event: Dict[str, Any]) -> None:
        """Handle text-delta event."""
        part_id = vsp_event.get("id")
        delta = vsp_event.get("delta", "")
        self.accumulator.add_delta(part_id, delta)
        return None

    def _handle_text_end(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle text-end event."""
        part_id = vsp_event.get("id")
        return self.accumulator.finalize_part(part_id)

    def _handle_reasoning_start(self, vsp_event: Dict[str, Any]) -> None:
        """Handle reasoning-start event."""
        part_id = vsp_event.get("id")
        metadata = {
            "agent_id": self.current_agent_id,
            "provider_name": vsp_event.get("providerName", "unknown")
        }
        self.accumulator.start_part(part_id, "thinking", metadata)
        return None

    def _handle_reasoning_delta(self, vsp_event: Dict[str, Any]) -> None:
        """Handle reasoning-delta event."""
        part_id = vsp_event.get("id")
        delta = vsp_event.get("delta", "")
        self.accumulator.add_delta(part_id, delta)
        return None

    def _handle_reasoning_end(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle reasoning-end event."""
        part_id = vsp_event.get("id")
        return self.accumulator.finalize_part(part_id)

    def _handle_tool_input_start(self, vsp_event: Dict[str, Any]) -> None:
        """Handle tool-input-start event."""
        part_id = vsp_event.get("id")
        metadata = {
            "agent_id": self.current_agent_id,
            "tool_call_id": vsp_event.get("toolCallId"),
            "tool_name": vsp_event.get("toolName")
        }
        self.accumulator.start_part(part_id, "tool_call", metadata)
        return None

    def _handle_tool_input_delta(self, vsp_event: Dict[str, Any]) -> None:
        """Handle tool-input-delta event."""
        part_id = vsp_event.get("id")
        delta = vsp_event.get("delta", "")
        self.accumulator.add_delta(part_id, delta)
        return None

    def _handle_tool_input_available(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool-input-available event."""
        part_id = vsp_event.get("id")
        event = self.accumulator.finalize_part(part_id)

        if event:
            # Parse args from accumulated content
            try:
                event["args"] = json.loads(event["content"])
                del event["content"]  # Remove raw JSON string
            except json.JSONDecodeError:
                # Keep as string if invalid JSON
                pass

        return event

    def _handle_tool_output(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool-output-available event."""
        return {
            "event_type": "tool_result",
            "tool_call_id": vsp_event.get("toolCallId"),
            "tool_name": vsp_event.get("toolName"),
            "status": "success" if not vsp_event.get("isError") else "error",
            "result": vsp_event.get("output"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _handle_step_boundary(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle step boundary events."""
        event_type = "step_start" if vsp_event["type"] == "start-step" else "step_end"
        return {
            "event_type": event_type,
            "step_number": vsp_event.get("stepNumber"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _handle_error(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle error events."""
        return {
            "event_type": "error",
            "error_type": vsp_event.get("errorType", "unknown"),
            "error_message": vsp_event.get("message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def add_event(self, event: Dict[str, Any]):
        """Add a complete event to the thread.

        Args:
            event: ThreadProtocol event dict
        """
        if event:
            self.events.append(event)

    def to_jsonl(self) -> str:
        """Convert events to JSONL string.

        Returns:
            JSONL string (one event per line)
        """
        return "\n".join(json.dumps(event) for event in self.events)

    def get_events(self) -> List[Dict[str, Any]]:
        """Get all events.

        Returns:
            List of event dicts
        """
        return self.events.copy()


class ThreadPersistence:
    """Handles thread persistence to disk."""

    def __init__(self, base_path: Path):
        """Initialize persistence handler.

        Args:
            base_path: Base directory for thread storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_thread(self, thread_id: str, jsonl: str):
        """Save thread to disk.

        Args:
            thread_id: Thread identifier
            jsonl: ThreadProtocol JSONL content
        """
        filepath = self.base_path / f"{thread_id}.jsonl"
        filepath.write_text(jsonl)

    def load_thread(self, thread_id: str) -> Optional[List[Dict[str, Any]]]:
        """Load thread from disk.

        Args:
            thread_id: Thread identifier

        Returns:
            List of event dicts or None if not found
        """
        filepath = self.base_path / f"{thread_id}.jsonl"
        if not filepath.exists():
            return None

        events = []
        for line in filepath.read_text().strip().split("\n"):
            if line:
                events.append(json.loads(line))

        return events

    def list_threads(self) -> List[Dict[str, Any]]:
        """List all saved threads with metadata.

        Returns:
            List of thread metadata dicts
        """
        threads = []

        for filepath in self.base_path.glob("*.jsonl"):
            thread_id = filepath.stem

            # Read first and last lines for metadata
            lines = filepath.read_text().strip().split("\n")
            if not lines:
                continue

            first_event = json.loads(lines[0])
            last_event = json.loads(lines[-1]) if len(lines) > 1 else first_event

            # Extract preview from first user message
            preview = "No messages yet"
            for line in lines:
                event = json.loads(line)
                if event.get("event_type") == "user_message":
                    content = event.get("content", "")
                    preview = content[:100] + ("..." if len(content) > 100 else "")
                    break

            threads.append({
                "thread_id": thread_id,
                "created_at": first_event.get("timestamp"),
                "updated_at": last_event.get("timestamp"),
                "message_count": len(lines),
                "preview": preview,
                "blueprint": first_event.get("blueprint", {})
            })

        # Sort by most recent
        threads.sort(key=lambda t: t["updated_at"], reverse=True)

        return threads
