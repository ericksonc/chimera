"""Security layer for file operations - sandboxing and validation.

This module wraps BaseFileEditor with security constraints:
- Path traversal prevention (no escaping base_path)
- Pattern-based filtering (include/exclude lists)
- Size limits (prevent reading huge files)
- Agent-friendly error handling (ModelRetry exceptions)

The security layer is where we enforce the sandbox boundary.
"""

import fnmatch
from pathlib import Path
from typing import Optional

import pathspec
from pydantic_ai.exceptions import ModelRetry

from chimera_core.filesystem.editor import BaseFileEditor, PathInfo


class SecurityError(Exception):
    """Raised when a security validation fails.

    This is an internal exception that gets converted to ModelRetry
    for agent consumption.
    """

    pass


class AgentFileTools:
    """Security wrapper for BaseFileEditor with sandboxing and validation.

    This class enforces:
    1. Path sandboxing - all operations restricted to base_path
    2. Pattern filtering - include/exclude patterns for fine-grained control
    3. Size limits - prevent reading files that are too large
    4. Agent-friendly errors - ModelRetry for retryable errors

    Example:
        editor = LocalFileEditor()
        tools = AgentFileTools(
            editor=editor,
            base_path="/Users/me/agent_workspace",
            max_file_size=200_000,
            include_patterns=["*.txt", "*.md"],
            exclude_patterns=["*/archive/*", ".git/*"]
        )

        # This will work (within base_path, matches patterns)
        content = tools.read_file("notes/todo.txt")

        # This will raise ModelRetry (path traversal)
        content = tools.read_file("../../etc/passwd")

        # This will raise ModelRetry (doesn't match include patterns)
        content = tools.read_file("binary.exe")
    """

    def __init__(
        self,
        editor: BaseFileEditor,
        base_path: str,
        max_file_size: int = 200_000,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
    ):
        """Initialize AgentFileTools with security constraints.

        Args:
            editor: BaseFileEditor implementation to wrap
            base_path: Base directory for sandboxing (all paths must be within this)
            max_file_size: Maximum file size in bytes (default 200KB)
            include_patterns: Optional whitelist of glob patterns (e.g., ["*.txt", "docs/*"])
            exclude_patterns: Optional blacklist of glob patterns (e.g., ["*.exe", ".git/*"])
        """
        self.editor = editor
        self.base_path = Path(base_path).resolve()
        self.max_file_size = max_file_size
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []

        # Load .gitignore if it exists
        self.gitignore_spec = None
        gitignore_path = self.base_path / ".gitignore"
        if gitignore_path.exists() and gitignore_path.is_file():
            try:
                with open(gitignore_path, "r") as f:
                    self.gitignore_spec = pathspec.PathSpec.from_lines(
                        pathspec.patterns.gitwildmatch.GitWildMatchPattern, f
                    )
            except Exception:
                # Silently ignore errors reading .gitignore
                pass

        # Validate base_path exists
        if not self.base_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")
        if not self.base_path.is_dir():
            raise ValueError(f"Base path must be a directory: {base_path}")

    def _resolve_and_validate_path(self, path: str) -> Path:
        """Resolve path and validate it's within base_path.

        Args:
            path: Relative path from base_path

        Returns:
            Absolute Path object

        Raises:
            SecurityError: If path is outside base_path
        """
        # Resolve path relative to base_path
        file_path = (self.base_path / path).resolve()

        # Check if resolved path is within base_path
        try:
            file_path.relative_to(self.base_path)
        except ValueError:
            raise SecurityError(
                f"Path '{path}' resolves outside allowed base path. "
                f"Attempted to access: {file_path}"
            )

        return file_path

    def _check_patterns(self, path: str, is_dir: bool = False) -> None:
        """Check if path matches include/exclude patterns.

        Args:
            path: Relative path to check
            is_dir: True if path is a directory

        Raises:
            SecurityError: If path doesn't match patterns
        """
        # Normalize path for pattern matching (forward slashes)
        normalized_path = str(Path(path).as_posix())

        # If it's a directory, append slash for .gitignore directory matching
        check_path = normalized_path + "/" if is_dir else normalized_path

        # Check exclude patterns first (blacklist takes precedence)
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(normalized_path, pattern):
                raise SecurityError(f"Path '{path}' matches exclude pattern '{pattern}'")

        # Check .gitignore if present
        if self.gitignore_spec:
            if self.gitignore_spec.match_file(check_path):
                raise SecurityError(f"Path '{path}' is ignored by .gitignore")

        # If include patterns specified, must match at least one (whitelist)
        if self.include_patterns:
            matches = any(
                fnmatch.fnmatch(normalized_path, pattern) for pattern in self.include_patterns
            )
            if not matches:
                raise SecurityError(
                    f"Path '{path}' does not match any include pattern. "
                    f"Allowed patterns: {', '.join(self.include_patterns)}"
                )

    def read_file(self, path: str) -> str:
        """Read a file with security checks.

        Args:
            path: Relative path from base_path (e.g., "notes/todo.txt")

        Returns:
            File contents as string

        Raises:
            ModelRetry: If security validation fails, file not found, or file too large
        """
        try:
            # Security checks
            file_path = self._resolve_and_validate_path(path)
            self._check_patterns(path)

            # Check file exists
            if not self.editor.file_exists(str(file_path)):
                raise ModelRetry(f"File not found: {path}")

            # Read file
            result = self.editor.read_file(str(file_path))

            # Check size limit
            if result.size_bytes > self.max_file_size:
                raise ModelRetry(
                    f"File '{path}' is too large ({result.size_bytes:,} bytes). "
                    f"Maximum size is {self.max_file_size:,} bytes."
                )

            return result.content

        except SecurityError as e:
            raise ModelRetry(f"Access denied: {str(e)}")
        except FileNotFoundError:
            raise ModelRetry(f"File not found: {path}")
        except UnicodeDecodeError:
            raise ModelRetry(f"File '{path}' appears to be binary. Only text files can be read.")
        except PermissionError:
            raise ModelRetry(f"Permission denied: {path}")
        except Exception as e:
            raise ModelRetry(f"Error reading file '{path}': {str(e)}")

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file with security checks.

        Args:
            path: Relative path from base_path
            content: Content to write

        Returns:
            Success message with diff for existing files

        Raises:
            ModelRetry: If security validation fails or write fails
        """
        try:
            # Security checks
            file_path = self._resolve_and_validate_path(path)
            self._check_patterns(path)

            # Write file
            result = self.editor.write_file(str(file_path), content)

            if result.was_created:
                return f"File created successfully: {path} ({result.bytes_written:,} bytes)"
            else:
                return f"File updated successfully: {path} ({result.bytes_written:,} bytes)"

        except SecurityError as e:
            raise ModelRetry(f"Access denied: {str(e)}")
        except PermissionError:
            raise ModelRetry(f"Permission denied: {path}")
        except Exception as e:
            raise ModelRetry(f"Error writing file '{path}': {str(e)}")

    def edit_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """Edit a file by replacing old_string with new_string.

        Args:
            path: Relative path from base_path
            old_string: Exact text to find and replace
            new_string: Text to replace it with
            replace_all: If True, replace all occurrences

        Returns:
            Unified diff showing changes

        Raises:
            ModelRetry: If security validation fails or edit fails
        """
        try:
            # Security checks
            file_path = self._resolve_and_validate_path(path)
            self._check_patterns(path)

            # Check file exists
            if not self.editor.file_exists(str(file_path)):
                raise ModelRetry(f"File not found: {path}")

            # Perform edit
            diff = self.editor.edit_file(str(file_path), old_string, new_string, replace_all)

            return f"File edited successfully: {path}\n\n{diff}"

        except SecurityError as e:
            raise ModelRetry(f"Access denied: {str(e)}")
        except FileNotFoundError:
            raise ModelRetry(f"File not found: {path}")
        except ValueError as e:
            raise ModelRetry(f"Edit failed: {str(e)}")
        except PermissionError:
            raise ModelRetry(f"Permission denied: {path}")
        except Exception as e:
            raise ModelRetry(f"Error editing file '{path}': {str(e)}")

    def list_all_paths(self, recursive: bool = True, prefix: str = "") -> list[PathInfo]:
        """List all accessible paths (respects include/exclude patterns).

        Args:
            recursive: If True, list recursively
            prefix: Optional prefix to filter results (e.g., "docs" to list only docs/)

        Returns:
            List of PathInfo objects with relative paths, types, and timestamps

        Raises:
            ModelRetry: If listing fails
        """
        try:
            # Determine starting path
            if prefix:
                # Validate prefix path
                start_path = self._resolve_and_validate_path(prefix)
            else:
                start_path = self.base_path

            # List all paths
            all_paths = self.editor.list_paths(str(start_path), recursive=recursive)

            # Filter by patterns
            filtered = []
            for path_info in all_paths:
                # Construct full relative path from base_path
                if prefix:
                    full_rel_path = str(Path(prefix) / path_info.path)
                else:
                    full_rel_path = path_info.path

                try:
                    is_dir = path_info.type == "directory"
                    self._check_patterns(full_rel_path, is_dir=is_dir)
                    # Update path_info with full relative path
                    filtered.append(
                        PathInfo(
                            path=full_rel_path,
                            type=path_info.type,
                            last_modified=path_info.last_modified,
                        )
                    )
                except SecurityError:
                    # Skip paths that don't match patterns
                    continue

            return filtered

        except SecurityError as e:
            raise ModelRetry(f"Access denied: {str(e)}")
        except Exception as e:
            raise ModelRetry(f"Error listing paths: {str(e)}")

    def file_exists(self, path: str) -> bool:
        """Check if a file exists (with security validation).

        Args:
            path: Relative path from base_path

        Returns:
            True if file exists and passes security checks, False otherwise
        """
        try:
            file_path = self._resolve_and_validate_path(path)
            self._check_patterns(path)
            return self.editor.file_exists(str(file_path))
        except (SecurityError, Exception):
            return False

    def create_directory(self, path: str) -> str:
        """Create a directory with security checks.

        Args:
            path: Relative path from base_path

        Returns:
            Success message

        Raises:
            ModelRetry: If security validation fails or creation fails
        """
        try:
            # Security checks
            dir_path = self._resolve_and_validate_path(path)
            self._check_patterns(path, is_dir=True)

            # Create directory
            self.editor.create_directory(str(dir_path))

            return f"Directory created successfully: {path}"

        except SecurityError as e:
            raise ModelRetry(f"Access denied: {str(e)}")
        except PermissionError:
            raise ModelRetry(f"Permission denied: {path}")
        except Exception as e:
            raise ModelRetry(f"Error creating directory '{path}': {str(e)}")
