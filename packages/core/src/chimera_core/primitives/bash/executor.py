"""Bash executor layer - pure execution without security constraints.

This module provides an ABC for bash execution and a local implementation.
No security checks are performed at this layer - that's the job of the security layer.

The design allows for alternative implementations (Docker, SSH, K8s pods, etc.) by
subclassing BaseBashExecutor.
"""

import asyncio
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class BashResult:
    """Result from a bash command execution."""

    stdout: str
    stderr: str
    exit_code: int
    command: str
    cwd: str

    @property
    def success(self) -> bool:
        """True if command exited with code 0."""
        return self.exit_code == 0

    @property
    def combined_output(self) -> str:
        """Combined stdout and stderr with exit code if non-zero."""
        output = self.stdout
        if self.stderr:
            output += "\n[STDERR]\n" + self.stderr
        if self.exit_code != 0:
            output = f"[Exit code: {self.exit_code}]\n{output}"
        return output.strip() if output else "(no output)"


class BaseBashExecutor(ABC):
    """Abstract base class for bash command execution.

    This is intentionally minimal and has NO security constraints.
    Security enforcement happens in the AgentBashTools wrapper.

    Implementations should:
    - Execute commands in specified working directory
    - Capture stdout and stderr separately
    - Return exit code
    - Raise subprocess.TimeoutExpired on timeout
    - Use UTF-8 encoding by default
    """

    @abstractmethod
    async def execute(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: int = 60,
    ) -> BashResult:
        """Execute a bash command.

        Args:
            command: Shell command to execute
            cwd: Working directory (defaults to current directory)
            timeout: Timeout in seconds (default 60)

        Returns:
            BashResult with stdout, stderr, and exit code

        Raises:
            subprocess.TimeoutExpired: If command times out
            Exception: For other execution errors
        """
        pass


class LocalBashExecutor(BaseBashExecutor):
    """Local subprocess-based bash executor.

    Executes commands on the local machine using subprocess.run.

    Example:
        executor = LocalBashExecutor()
        result = await executor.execute("ls -la", cwd=Path("/tmp"))
        print(result.combined_output)
    """

    async def execute(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: int = 60,
    ) -> BashResult:
        """Execute a bash command using subprocess.

        Args:
            command: Shell command to execute
            cwd: Working directory (defaults to current directory)
            timeout: Timeout in seconds (default 60)

        Returns:
            BashResult with stdout, stderr, and exit code

        Raises:
            subprocess.TimeoutExpired: If command times out
            Exception: For other execution errors
        """
        try:
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    cwd=str(cwd) if cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                ),
            )

            return BashResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                command=command,
                cwd=str(cwd) if cwd else str(Path.cwd()),
            )

        except subprocess.TimeoutExpired as e:
            raise subprocess.TimeoutExpired(
                cmd=command, timeout=timeout, output=e.output, stderr=e.stderr
            )
        except Exception:
            # Let other exceptions propagate
            raise
