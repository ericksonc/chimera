"""Configuration management for CLI.

Handles loading and saving CLI settings like last used blueprint, server URL, etc.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class CLIConfig:
    """Manages CLI configuration."""

    DEFAULT_CONFIG = {
        "server_url": "http://localhost:33003",
        "last_blueprint_path": None,
        "last_blueprint_name": None,
        "last_blueprint_file": None,
        "last_thread_id": None,
        "display_thinking": True,
        "auto_save": True,
    }

    def __init__(self, config_path: Path):
        """Initialize config manager.

        Args:
            config_path: Path to config JSON file
        """
        self.config_path = Path(config_path)
        self.config = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load config from disk.

        Returns:
            Config dict (defaults if file doesn't exist)
        """
        if not self.config_path.exists():
            return self.DEFAULT_CONFIG.copy()

        try:
            return json.loads(self.config_path.read_text())
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load config from {self.config_path}: {e}")
            return self.DEFAULT_CONFIG.copy()

    def save(self):
        """Save current config to disk."""
        try:
            # Ensure parent directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write config
            self.config_path.write_text(json.dumps(self.config, indent=2))
        except IOError as e:
            print(f"Warning: Failed to save config to {self.config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value.

        Args:
            key: Config key
            default: Default value if key not found

        Returns:
            Config value
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any, save: bool = True):
        """Set config value.

        Args:
            key: Config key
            value: Config value
            save: Whether to save to disk immediately
        """
        self.config[key] = value
        if save:
            self.save()

    @property
    def server_url(self) -> str:
        """Get server URL."""
        return self.config.get("server_url", self.DEFAULT_CONFIG["server_url"])

    @server_url.setter
    def server_url(self, value: str):
        """Set server URL."""
        self.set("server_url", value)

    @property
    def last_blueprint_path(self) -> Optional[str]:
        """Get last used blueprint path."""
        return self.config.get("last_blueprint_path")

    @last_blueprint_path.setter
    def last_blueprint_path(self, value: Optional[str]):
        """Set last used blueprint path."""
        self.set("last_blueprint_path", value)

    @property
    def last_blueprint_name(self) -> Optional[str]:
        """Get last used blueprint name."""
        return self.config.get("last_blueprint_name")

    @last_blueprint_name.setter
    def last_blueprint_name(self, value: Optional[str]):
        """Set last used blueprint name."""
        self.set("last_blueprint_name", value)

    @property
    def last_blueprint_file(self) -> Optional[str]:
        """Get last used blueprint filename."""
        return self.config.get("last_blueprint_file")

    @last_blueprint_file.setter
    def last_blueprint_file(self, value: Optional[str]):
        """Set last used blueprint filename."""
        self.set("last_blueprint_file", value)

    @property
    def last_thread_id(self) -> Optional[str]:
        """Get last active thread ID."""
        return self.config.get("last_thread_id")

    @last_thread_id.setter
    def last_thread_id(self, value: Optional[str]):
        """Set last active thread ID."""
        self.set("last_thread_id", value)

    @property
    def display_thinking(self) -> bool:
        """Whether to display thinking/reasoning."""
        return self.config.get("display_thinking", True)

    @display_thinking.setter
    def display_thinking(self, value: bool):
        """Set display thinking flag."""
        self.set("display_thinking", value)

    @property
    def auto_save(self) -> bool:
        """Whether to auto-save threads."""
        return self.config.get("auto_save", True)

    @auto_save.setter
    def auto_save(self, value: bool):
        """Set auto-save flag."""
        self.set("auto_save", value)
