"""ThreadProtocol Reader - Reads events from JSONL files.

This handles reading and parsing ThreadProtocol events from JSONL files.
Supports reading all events, filtering by type, and extracting the blueprint.
"""

import json
from pathlib import Path
from typing import Iterator, Optional


class ThreadProtocolReader:
    """Reads events from ThreadProtocol JSONL file.

    Usage:
        reader = ThreadProtocolReader("thread-123.jsonl")

        # Read all events
        for event in reader.read_all():
            print(event["event_type"])

        # Read only specific event types
        for event in reader.read_filtered({"user_message", "text"}):
            print(event["content"])

        # Get blueprint (Line 1)
        blueprint = reader.read_blueprint()
    """

    def __init__(self, file_path: str | Path):
        """Initialize reader with file path.

        Args:
            file_path: Path to JSONL file to read
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"ThreadProtocol file not found: {file_path}")

    def read_all(self) -> Iterator[dict]:
        """Read all events from the file.

        Yields:
            Event dictionaries in order
        """
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON at line {line_num} in {self.file_path}: {e}"
                    ) from e

    def read_filtered(self, event_types: set[str]) -> Iterator[dict]:
        """Read only events of specific types.

        Args:
            event_types: Set of event types to include

        Yields:
            Event dictionaries matching the filter
        """
        for event in self.read_all():
            if event.get("event_type") in event_types:
                yield event

    def read_blueprint(self) -> dict | None:
        """Read the blueprint event (should be Line 1).

        Returns:
            Blueprint event dict, or None if not found
        """
        for event in self.read_all():
            if event.get("event_type") == "thread_blueprint":
                return event
            # Blueprint should be first, so if we see another type, stop
            break
        return None

    def read_conversation_events(self) -> Iterator[dict]:
        """Read only conversation events (skip structural/system events).

        This filters to just the events that represent actual conversation content.

        Yields:
            User messages, agent responses, tool calls/results
        """
        conversation_types = {
            "user_message",
            "text",
            "thinking",
            "tool_call",
            "tool_result",
            "tool_error"
        }
        return self.read_filtered(conversation_types)

    def read_turn_events(self, turn_number: int) -> list[dict]:
        """Read all events for a specific turn.

        Args:
            turn_number: Turn number to read (0-based)

        Returns:
            List of events in that turn
        """
        current_turn = -1  # Start before turn 0
        turn_events = []
        collecting = False

        for event in self.read_all():
            event_type = event.get("event_type", "")

            # Track turn boundaries
            if event_type == "user_turn_start":
                current_turn += 1
                if current_turn == turn_number:
                    collecting = True
                elif collecting:
                    # We've passed the turn we want
                    break

            # Collect events if we're in the right turn
            if collecting:
                turn_events.append(event)

        return turn_events

    def count_turns(self) -> int:
        """Count the number of complete turns in the thread.

        Returns:
            Number of complete turns (user + agent)
        """
        turn_count = 0
        for event in self.read_filtered({"user_turn_start"}):
            turn_count += 1
        return turn_count

    def get_usage_stats(self) -> dict:
        """Calculate total token usage from the thread.

        Returns:
            Dict with input_tokens, output_tokens, reasoning_tokens, total_tokens
        """
        stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0
        }

        for event in self.read_filtered({"usage", "step_end"}):
            if "usage" in event:
                usage = event["usage"]
                stats["input_tokens"] += usage.get("input_tokens", 0)
                stats["output_tokens"] += usage.get("output_tokens", 0)
                stats["reasoning_tokens"] += usage.get("reasoning_tokens", 0)

        stats["total_tokens"] = stats["input_tokens"] + stats["output_tokens"]
        return stats

    def tail_follow(self, poll_interval: float = 0.1) -> Iterator[dict]:
        """Follow the file for new events (like tail -f).

        This is useful for watching a thread in real-time.

        Args:
            poll_interval: Seconds between file checks

        Yields:
            New events as they are written
        """
        import time

        # Start from current end of file
        with open(self.file_path, 'r', encoding='utf-8') as f:
            # Seek to end
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass  # Skip malformed lines
                else:
                    time.sleep(poll_interval)