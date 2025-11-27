"""File editor layer - pure I/O operations without security constraints.

This module provides an ABC for file operations and a local filesystem implementation.
No security checks are performed at this layer - that's the job of the security layer.

The design allows for alternative implementations (cloud storage, git, etc.) by
subclassing BaseFileEditor.
"""

import difflib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class FileReadResult:
    """Result from a file read operation."""

    content: str
    path: str  # Absolute path
    size_bytes: int
    encoding: str = "utf-8"


@dataclass
class FileWriteResult:
    """Result from a file write operation."""

    path: str  # Absolute path
    bytes_written: int
    was_created: bool  # True if new file, False if overwritten


@dataclass
class PathInfo:
    """Information about a file or directory."""

    path: str  # Relative to base_path
    type: str  # "file" or "directory"
    last_modified: str  # Human-readable relative time


class BaseFileEditor(ABC):
    """Abstract base class for file I/O operations.

    This is intentionally minimal and has NO security constraints.
    Security enforcement happens in the AgentFileTools wrapper.

    Implementations should:
    - Raise FileNotFoundError if file doesn't exist
    - Raise UnicodeDecodeError if file is binary
    - Raise PermissionError if access denied
    - Use UTF-8 encoding by default
    """

    @abstractmethod
    def read_file(self, path: str) -> FileReadResult:
        """Read a file and return its contents.

        Args:
            path: Absolute path to file

        Returns:
            FileReadResult with content and metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If file is binary
            PermissionError: If access denied
        """
        pass

    @abstractmethod
    def write_file(self, path: str, content: str) -> FileWriteResult:
        """Write content to a file (create new or overwrite existing).

        Args:
            path: Absolute path to file
            content: Content to write

        Returns:
            FileWriteResult with metadata

        Raises:
            PermissionError: If access denied
        """
        pass

    @abstractmethod
    def edit_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """Perform exact string replacement in a file.

        Args:
            path: Absolute path to file
            old_string: Exact text to find and replace
            new_string: Text to replace it with
            replace_all: If True, replace all occurrences

        Returns:
            Unified diff showing the changes

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If old_string not found or not unique (when replace_all=False)
        """
        pass

    @abstractmethod
    def list_paths(self, base_path: str, recursive: bool = False) -> list[PathInfo]:
        """List files and directories.

        Args:
            base_path: Directory to list
            recursive: If True, list recursively

        Returns:
            List of PathInfo objects with metadata
        """
        pass

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists.

        Args:
            path: Absolute path to check

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    def create_directory(self, path: str) -> None:
        """Create a directory (and parent directories if needed).

        Args:
            path: Absolute path to directory

        Raises:
            PermissionError: If access denied
        """
        pass


class LocalFileEditor(BaseFileEditor):
    """Local filesystem implementation of BaseFileEditor.

    Operates on files using standard Python file I/O.
    No security constraints - path validation happens in AgentFileTools.
    """

    def __init__(self, base_path: Optional[str] = None):
        """Initialize LocalFileEditor.

        Args:
            base_path: Optional base directory for relative path resolution.
                      If not provided, paths must be absolute.
        """
        self.base_path = Path(base_path).resolve() if base_path else None

    def _resolve_path(self, path: str) -> Path:
        """Convert path to absolute Path object.

        If base_path is set, relative paths are resolved against it.
        Absolute paths are used as-is.
        """
        path_obj = Path(path)

        if path_obj.is_absolute():
            return path_obj

        if self.base_path:
            return self.base_path / path_obj

        # No base_path and path is relative - use cwd
        return path_obj.resolve()

    def read_file(self, path: str) -> FileReadResult:
        """Read file from local filesystem."""
        file_path = self._resolve_path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        # Read with UTF-8 encoding (will raise UnicodeDecodeError for binary files)
        content = file_path.read_text(encoding="utf-8")

        return FileReadResult(
            content=content,
            path=str(file_path),
            size_bytes=len(content.encode("utf-8")),
            encoding="utf-8",
        )

    def write_file(self, path: str, content: str) -> FileWriteResult:
        """Write content to local filesystem."""
        file_path = self._resolve_path(path)
        was_created = not file_path.exists()

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        return FileWriteResult(
            path=str(file_path), bytes_written=len(content.encode("utf-8")), was_created=was_created
        )

    def edit_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """Perform exact string replacement in file."""
        file_path = self._resolve_path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if old_string == new_string:
            raise ValueError("old_string and new_string must be different")

        # Read current content
        content = file_path.read_text(encoding="utf-8")

        # Check if old_string exists
        occurrences = content.count(old_string)
        if occurrences == 0:
            raise ValueError(f"old_string not found in file: {path}")

        if not replace_all and occurrences > 1:
            raise ValueError(
                f"old_string appears {occurrences} times in file. "
                "Either provide a more specific old_string or use replace_all=True"
            )

        # Perform replacement
        new_content = content.replace(old_string, new_string)

        # Write back
        file_path.write_text(new_content, encoding="utf-8")

        # Generate unified diff
        diff = self._generate_diff(content, new_content, str(file_path))
        return diff

    def list_paths(self, base_path: str, recursive: bool = False) -> list[PathInfo]:
        """List files and directories in local filesystem."""
        base_path_obj = self._resolve_path(base_path)

        if not base_path_obj.exists():
            return []

        if not base_path_obj.is_dir():
            raise ValueError(f"Path is not a directory: {base_path}")

        items = []
        now = datetime.now()

        # Choose iteration method
        iterator = base_path_obj.rglob("*") if recursive else base_path_obj.iterdir()

        for item in iterator:
            try:
                # Get relative path from base_path
                rel_path = item.relative_to(base_path_obj)

                # Get modification time
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                time_str = self._format_relative_time(now, mtime)

                items.append(
                    PathInfo(
                        path=str(rel_path),
                        type="directory" if item.is_dir() else "file",
                        last_modified=time_str,
                    )
                )
            except (OSError, ValueError):
                # Skip files with errors (permissions, etc.)
                continue

        return sorted(items, key=lambda x: x.path)

    def file_exists(self, path: str) -> bool:
        """Check if file exists in local filesystem."""
        file_path = self._resolve_path(path)
        return file_path.exists() and file_path.is_file()

    def create_directory(self, path: str) -> None:
        """Create directory in local filesystem."""
        dir_path = self._resolve_path(path)
        dir_path.mkdir(parents=True, exist_ok=True)

    def _format_relative_time(self, now: datetime, then: datetime) -> str:
        """Format time difference as human-readable relative time."""
        diff = now - then
        seconds = diff.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        elif seconds < 31536000:
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = int(seconds / 31536000)
            return f"{years} year{'s' if years != 1 else ''} ago"

    def _generate_diff(
        self, old_content: str, new_content: str, filename: str, context_lines: int = 2
    ) -> str:
        """Generate unified diff between old and new content."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
            n=context_lines,
        )

        return "".join(diff)
