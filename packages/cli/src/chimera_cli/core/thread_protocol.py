"""ThreadProtocol v0.0.7 handler for CLI.

Handles building ThreadProtocol JSONL from VSP events and persisting threads.

Key changes in v0.0.7:
- Uses EventCondenser from core.threadprotocol.condensation for delta handling
- Agent IDs are strings (not UUIDs)
- Multi-agent events use data-agent-start/finish (not agent-turn-start/end)
- Text/reasoning deltas condense to text-complete/reasoning-complete events
- State mutations use nested data structure
- Tool approval events added
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chimera_core.threadprotocol.blueprint import THREAD_PROTOCOL_VERSION
from chimera_core.threadprotocol.condensation import EventCondenser
from chimera_core.threadprotocol.validation import validate_event_ordering

logger = logging.getLogger(__name__)


class ThreadProtocolBuilder:
    """Builds ThreadProtocol JSONL from VSP events."""

    def __init__(self, blueprint_event: Dict[str, Any], persist_path: Optional[Path] = None):
        """Initialize builder with blueprint.

        Args:
            blueprint_event: BlueprintProtocol event (first line of JSONL)
            persist_path: Optional path for incremental JSONL writes (append mode)
        """
        self.events: List[Dict[str, Any]] = [blueprint_event]
        self.condenser = EventCondenser()
        self.current_agent_id: Optional[str] = None
        self.pending_tool_calls: Dict[str, Dict[str, Any]] = {}  # tool_call_id -> tool_call event
        self.persist_path = persist_path

        # Write blueprint immediately if persist_path is set
        if self.persist_path:
            self._append_event_to_disk(blueprint_event)

    def process_vsp_event(self, vsp_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a VSP event and return ThreadProtocol event if complete.

        Args:
            vsp_event: VSP event from SSE stream

        Returns:
            ThreadProtocol event if one should be written, None otherwise
        """
        event_type = vsp_event.get("type")

        # Skip message boundaries - not saved to JSONL in v0.0.7
        if event_type in ("start", "finish", "abort"):
            return None

        # Let condenser handle text/reasoning/tool-input deltas
        condensed = self.condenser.process_event(vsp_event)

        # If condenser returned an event, it's ready for JSONL
        if condensed:
            # Track current agent for context
            if condensed["type"] == "data-agent-start":
                data = condensed.get("data", {})
                self.current_agent_id = data.get("agentId")

            # Track pending tools for approval flow
            elif condensed["type"] == "tool-input-available":
                tool_call_id = condensed.get("toolCallId")
                if tool_call_id:
                    self.pending_tool_calls[tool_call_id] = condensed

            # Clear pending tool on result
            elif condensed["type"] in (
                "tool-output-available",
                "tool-output-denied",
                "tool-output-error",
            ):
                tool_call_id = condensed.get("toolCallId")
                if tool_call_id and tool_call_id in self.pending_tool_calls:
                    del self.pending_tool_calls[tool_call_id]

            return condensed

        # Handle custom Chimera events not handled by condenser
        if event_type in ("data-agent-start", "data-agent-finish"):
            return self._handle_agent_boundary(vsp_event)

        if event_type in ("data-user-turn-start", "data-user-message", "data-user-turn-end"):
            return self._handle_user_turn(vsp_event)

        if event_type == "data-app-chimera":
            return self._handle_state_mutation(vsp_event)

        if event_type == "tool-approval-request":
            return self._handle_tool_approval_request(vsp_event)

        if event_type == "data-tool-approval-response":
            return self._handle_tool_approval_response(vsp_event)

        # Step boundaries
        if event_type in ("start-step", "finish-step"):
            return self._handle_step_boundary(vsp_event)

        # Errors
        if event_type == "error":
            return self._handle_error(vsp_event)

        # Condenser returned None - event is being accumulated or skipped
        return None

    def _handle_agent_boundary(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle data-agent-start and data-agent-finish events."""
        event_type = vsp_event["type"]
        data = vsp_event.get("data", {})

        # Track current agent for context
        if event_type == "data-agent-start":
            self.current_agent_id = data.get("agentId")

        # Pass through unchanged - already in correct v0.0.7 format
        return vsp_event

    def _handle_user_turn(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user turn events (data-user-turn-start, data-user-message, data-user-turn-end)."""
        # Pass through unchanged - already in correct v0.0.7 format
        return vsp_event

    def _handle_tool_approval_request(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool-approval-request events."""
        # Pass through unchanged - VSP v6 format
        return vsp_event

    def _handle_tool_approval_response(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle data-tool-approval-response events.

        v0.0.7: Persists user approval decisions to JSONL for audit trail.
        Format: {"type": "data-tool-approval-response", "toolCallId": "...", "approved": bool, "reason": "..."}
        """
        # Pass through unchanged - already in correct v0.0.7 format
        return vsp_event

    def _handle_state_mutation(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle state mutation events (data-app-chimera).

        v0.0.7 format: {"type": "data-app-chimera", "data": {"source": "...", "payload": {...}}}
        """
        # Pass through unchanged - already in correct v0.0.7 format
        return vsp_event

    def _handle_step_boundary(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle step boundary events."""
        # Pass through VSP event type unchanged
        return {
            "type": vsp_event["type"],  # "start-step" or "finish-step"
            "stepNumber": vsp_event.get("stepNumber"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_error(self, vsp_event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle error events."""
        return {
            "type": "error",
            "errorType": vsp_event.get("errorType", "unknown"),
            "message": vsp_event.get("message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def add_event(self, event: Dict[str, Any]):
        """Add a complete event to the thread.

        Args:
            event: ThreadProtocol event dict
        """
        if event:
            self.events.append(event)
            # Incrementally write if persist_path is configured
            if self.persist_path:
                self._append_event_to_disk(event)

    def _append_event_to_disk(self, event: Dict[str, Any]):
        """Append a single event to the JSONL file.

        This enables incremental persistence - events are written as they arrive
        rather than all at once at the end. Protects against data loss on crashes.

        Args:
            event: ThreadProtocol event dict to append
        """
        if self.persist_path:
            # Ensure parent directory exists
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)

            # Append event as a new line
            with open(self.persist_path, "a") as f:
                f.write(json.dumps(event) + "\n")

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

    def get_pending_tools(self) -> List[Dict[str, Any]]:
        """Get tool calls that are pending execution (awaiting approval).

        Returns:
            List of tool_call events that don't have corresponding tool_result events
        """
        return list(self.pending_tool_calls.values())

    def consume_pending_tools(self) -> List[Dict[str, Any]]:
        """Get and clear pending tool calls atomically.

        This should be called when tools transition from "pending execution"
        to "awaiting approval" state to prevent re-prompting.

        Returns:
            List of tool_call events that were pending
        """
        pending = list(self.pending_tool_calls.values())
        self.pending_tool_calls.clear()
        return pending


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
        """Load thread from disk with error handling for malformed JSONL.

        Args:
            thread_id: Thread identifier

        Returns:
            List of event dicts or None if not found

        Raises:
            ValueError: If JSONL contains malformed JSON lines (after logging errors)
        """
        filepath = self.base_path / f"{thread_id}.jsonl"
        if not filepath.exists():
            return None

        events = []
        errors = []
        lines = filepath.read_text().strip().split("\n")

        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue

            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                error_msg = f"Line {line_no}: {e}"
                errors.append(error_msg)
                logger.error(
                    f"Skipping malformed JSON in thread {thread_id} at line {line_no}: {e}"
                )
                continue

        if errors:
            logger.warning(
                f"Loaded thread {thread_id} with {len(events)} events and {len(errors)} parsing errors"
            )
            # For now, we allow partial recovery. Future: could raise exception
            # raise ValueError(f"Thread {thread_id} has malformed JSONL: {errors}")

        # Validate ThreadProtocol version from blueprint event (first line)
        if events and events[0].get("type") == "thread-blueprint":
            thread_protocol_version = events[0].get("threadProtocolVersion", "0.0.1")
            if thread_protocol_version != THREAD_PROTOCOL_VERSION:
                raise ValueError(
                    f"ThreadProtocol version mismatch in thread {thread_id}: "
                    f"expected {THREAD_PROTOCOL_VERSION}, got {thread_protocol_version}. "
                    f"This thread may require migration or was created with an incompatible version."
                )

        # Validate event ordering (tool calls before outputs, no duplicates)
        if events:
            validation_result = validate_event_ordering(events, strict=False)
            if not validation_result.success:
                for error in validation_result.errors:
                    logger.error(f"Thread {thread_id} ordering error: {error}")
                logger.error(
                    f"Thread {thread_id} has {len(validation_result.errors)} event ordering errors"
                )
                # For now, log errors but don't fail (permissive mode)
                # Future: could raise ValueError in strict mode
            if validation_result.warnings:
                for warning in validation_result.warnings:
                    logger.warning(f"Thread {thread_id}: {warning}")

        return events

    def list_threads(self) -> List[Dict[str, Any]]:
        """List all saved threads with metadata.

        Returns:
            List of thread metadata dicts (skips threads with malformed JSONL)
        """
        threads = []

        for filepath in self.base_path.glob("*.jsonl"):
            thread_id = filepath.stem

            try:
                # Read first and last lines for metadata
                lines = filepath.read_text().strip().split("\n")
                if not lines:
                    continue

                first_event = json.loads(lines[0])
                last_event = json.loads(lines[-1]) if len(lines) > 1 else first_event

                # Extract preview from first user message
                preview = "No messages yet"
                for line in lines:
                    try:
                        event = json.loads(line)
                        # v0.0.7: data-user-message with content in data field
                        if event.get("type") == "data-user-message":
                            content = event.get("data", {}).get("content", "")
                            preview = content[:100] + ("..." if len(content) > 100 else "")
                            break
                    except json.JSONDecodeError:
                        # Skip malformed lines when extracting preview
                        continue

                threads.append(
                    {
                        "thread_id": thread_id,
                        "created_at": first_event.get("timestamp"),
                        "updated_at": last_event.get("timestamp"),
                        "message_count": len(lines),
                        "preview": preview,
                        "blueprint": first_event.get("blueprint", {}),
                    }
                )
            except (json.JSONDecodeError, IndexError) as e:
                # Skip threads with malformed JSONL or empty files
                logger.warning(f"Skipping thread {thread_id} in list_threads due to error: {e}")
                continue

        # Sort by most recent (handle None timestamps by treating as oldest)
        threads.sort(key=lambda t: t["updated_at"] or "", reverse=True)

        return threads
