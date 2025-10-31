"""Blueprint manager for CLI.

Handles loading blueprints from blueprints/*.json and tracking last used blueprint.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4


class BlueprintManager:
    """Manages blueprints for CLI."""

    def __init__(self, blueprints_dir: Path):
        """Initialize blueprint manager.

        Args:
            blueprints_dir: Directory containing blueprint JSON files
        """
        self.blueprints_dir = Path(blueprints_dir)

    def list_blueprints(self) -> List[Dict[str, Any]]:
        """List all available blueprints.

        Returns:
            List of blueprint metadata dicts
        """
        blueprints = []

        for filepath in self.blueprints_dir.glob("*.json"):
            try:
                blueprint_data = json.loads(filepath.read_text())

                # Extract metadata
                blueprint_info = {
                    "file_path": str(filepath),
                    "file_name": filepath.name,
                    "blueprint_data": blueprint_data,
                    "blueprint_version": blueprint_data.get("blueprint_version", "unknown"),
                }

                # Extract description from first agent if available
                agents = blueprint_data.get("blueprint", {}).get("agents", [])
                if agents:
                    first_agent = agents[0]
                    blueprint_info["name"] = first_agent.get("name", filepath.stem)
                    blueprint_info["description"] = first_agent.get("description", "No description")
                else:
                    blueprint_info["name"] = filepath.stem
                    blueprint_info["description"] = "No description"

                blueprints.append(blueprint_info)

            except (json.JSONDecodeError, KeyError) as e:
                # Skip invalid blueprints
                print(f"Warning: Failed to load blueprint {filepath}: {e}")
                continue

        return blueprints

    def load_blueprint(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load a specific blueprint.

        Args:
            file_path: Path to blueprint JSON file

        Returns:
            Blueprint data dict or None if not found/invalid
        """
        try:
            filepath = Path(file_path)
            if not filepath.exists():
                return None

            return json.loads(filepath.read_text())

        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading blueprint {file_path}: {e}")
            return None

    def create_thread_blueprint_event(
        self,
        blueprint_data: Dict[str, Any],
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create ThreadProtocol blueprint event from blueprint data.

        Args:
            blueprint_data: Raw blueprint data from JSON file
            thread_id: Optional thread ID (generates one if not provided)

        Returns:
            ThreadProtocol blueprint event dict
        """
        if thread_id is None:
            thread_id = str(uuid4())

        # If blueprint_data is already a thread_blueprint event, update it
        if blueprint_data.get("event_type") == "thread_blueprint":
            event = dict(blueprint_data)
            event["thread_id"] = thread_id
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
            return event

        # Otherwise, create new thread_blueprint event
        return {
            "event_type": "thread_blueprint",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "blueprint_version": blueprint_data.get("blueprint_version", "0.0.1"),
            "blueprint": blueprint_data.get("blueprint", blueprint_data)
        }

    def get_default_blueprint(self) -> Optional[Dict[str, Any]]:
        """Get the default blueprint (first one found).

        Returns:
            Blueprint data dict or None if no blueprints available
        """
        blueprints = self.list_blueprints()
        if not blueprints:
            return None

        return blueprints[0]["blueprint_data"]
