"""CronSummarizerSpace - Space for triggered document summarization.

This space is designed for non-interactive, scheduled execution:
1. Loads documents from an input directory
2. Agent summarizes them with structured output
3. Evaluates output via callback functions
4. Saves successful output to file, archives source documents

Usage:
    config = CronSummarizerConfig(
        prompt="Summarize all documents below. Keep 500-5000 chars.",
        base_path="/path/to/newsletter",
        input_directory="inbox",
        output_directory="summaries",
        evals=[length_check(500, 5000)]
    )
    space = CronSummarizerSpace(agent, config)
"""

from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel
from pydantic_ai.output import ToolOutput

from chimera_core.base_plugin import HookResult
from chimera_core.protocols.space_decision import TurnDecision
from chimera_core.spaces.generic_space import GenericSpace

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult
    from pydantic_graph.beta import StepContext

    from chimera_core.agent import Agent
    from chimera_core.threadprotocol.blueprint import ComponentConfig, SpaceConfig


# =============================================================================
# Output Types
# =============================================================================


class SummaryOutput(BaseModel):
    """Structured output from summarizer agent."""

    title: str
    summary: str
    key_points: list[str] | None = None


@dataclass
class AgentEval:
    """Result of evaluating agent output."""

    success: bool
    reason: str | None = None  # Required if success=False


# =============================================================================
# Eval Functions
# =============================================================================


def length_check(
    min_chars: int = 500, max_chars: int = 5000
) -> Callable[[SummaryOutput], AgentEval]:
    """Create a length-checking eval function.

    Args:
        min_chars: Minimum character count for summary
        max_chars: Maximum character count for summary

    Returns:
        Eval function that checks summary length
    """

    def check(output: SummaryOutput) -> AgentEval:
        length = len(output.summary)
        if length < min_chars:
            return AgentEval(
                success=False, reason=f"Summary too short: {length} chars (min: {min_chars})"
            )
        if length > max_chars:
            return AgentEval(
                success=False, reason=f"Summary too long: {length} chars (max: {max_chars})"
            )
        return AgentEval(success=True)

    return check


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class CronSummarizerConfig:
    """Configuration for CronSummarizerSpace."""

    # Prompt - becomes the UserMessage
    prompt: str  # e.g., "Summarize all documents. Keep between 500-5000 chars."

    # Paths (all relative to base_path)
    base_path: str  # e.g., "/Users/ericksonc/Documents/newsletter"
    input_directory: str  # e.g., "inbox" → base_path/inbox/
    output_directory: str  # e.g., "summaries" → base_path/summaries/
    archive_directory: str | None = None  # Default: output_directory + "/archive"

    # Evaluations (optional)
    evals: list[Callable[[SummaryOutput], AgentEval]] = field(default_factory=list)


# =============================================================================
# Space Implementation
# =============================================================================


class CronSummarizerSpace(GenericSpace):
    """Space for triggered document summarization.

    Extends GenericSpace with:
    - Structured output via ToolOutput
    - Document loading from input directory
    - Output evaluation with retry logic
    - File output and document archiving
    """

    component_version = "1.0.0"

    def __init__(self, agent: "Agent", config: CronSummarizerConfig):
        """Initialize CronSummarizerSpace.

        Args:
            agent: The summarizer agent
            config: Configuration for paths, prompt, and evals
        """
        super().__init__(agent)
        self.config = config
        self._documents: dict[str, str] = {}
        self._retry_count = 0
        self._last_eval_failure: str | None = None

        # Resolve archive directory
        if config.archive_directory is None:
            self.archive_dir = Path(config.base_path) / config.output_directory / "archive"
        else:
            self.archive_dir = Path(config.base_path) / config.archive_directory

    @property
    def output_type(self) -> type:
        """Return ToolOutput-wrapped schema for explicit structured output."""
        return ToolOutput(
            SummaryOutput,
            name="submit_summary",
            description="Submit your final summary with title, summary text, and optional key points.",
        )

    # =========================================================================
    # Document Loading (from ContextDocsWidget pattern)
    # =========================================================================

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is a text file based on extension and mime type."""
        # Skip files > 1MB (likely binary or generated)
        if file_path.exists():
            file_size = file_path.stat().st_size
            if file_size > 1_000_000:  # 1MB
                return False

        # Common text file extensions
        text_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".cs",
            ".go",
            ".rs",
            ".swift",
            ".sh",
            ".html",
            ".css",
            ".xml",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".md",
            ".rst",
            ".txt",
            ".sql",
        }

        # Check common filenames without extensions
        filename = file_path.name.lower()
        if filename in {"dockerfile", "makefile", "readme", "license", "changelog"}:
            return True

        # Check extension
        if file_path.suffix.lower() in text_extensions:
            return True

        # Fallback to mime type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type and mime_type.startswith("text/"):
            return True

        return False

    def load_input_documents(self) -> str:
        """Load documents from input directory, return formatted context.

        Uses same pattern as ContextDocsWidget.

        Returns:
            Formatted string with all documents for agent context
        """
        input_path = Path(self.config.base_path) / self.config.input_directory
        self._documents = {}

        if not input_path.exists():
            return "No documents found - input directory does not exist."

        for file_path in input_path.rglob("*"):
            if file_path.is_file() and self._is_text_file(file_path):
                # Skip hidden files
                if any(part.startswith(".") for part in file_path.relative_to(input_path).parts):
                    continue
                try:
                    rel_path = file_path.relative_to(input_path)
                    content = file_path.read_text(encoding="utf-8")
                    self._documents[str(rel_path)] = content
                except UnicodeDecodeError:
                    continue  # Skip binary files

        if not self._documents:
            return "No documents found in input directory."

        # Format for context
        lines = ["# DOCUMENTS TO SUMMARIZE", ""]
        for rel_path, content in sorted(self._documents.items()):
            lines.append(f"## {rel_path}")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Lifecycle Hooks
    # =========================================================================

    async def get_instructions(self, ctx: "StepContext") -> str:
        """Inject document context into agent."""
        return self.load_input_documents()

    async def on_agent_output(
        self, result: "AgentRunResult", ctx: "StepContext"
    ) -> HookResult | None:
        """Evaluate output and process if valid."""
        output: SummaryOutput = result.output

        # Run configured evals
        for eval_fn in self.config.evals:
            eval_result = eval_fn(output)
            if not eval_result.success:
                return self._handle_eval_failure(eval_result.reason or "Evaluation failed")

        # All evals passed - process output
        await self._process_output(output)
        return HookResult.continue_with()

    # =========================================================================
    # DecidableSpace Protocol
    # =========================================================================

    def should_continue_turn(self, last_output: Any) -> TurnDecision:
        """Retry with feedback if eval failed, otherwise complete."""
        if self._last_eval_failure:
            feedback = self._last_eval_failure
            self._last_eval_failure = None
            return TurnDecision(
                decision="continue",
                next_prompt=f"Your output did not pass evaluation.\n\nFeedback: {feedback}\n\nPlease try again.",
            )
        return TurnDecision(decision="complete")

    # =========================================================================
    # Output Processing
    # =========================================================================

    def _handle_eval_failure(self, reason: str) -> HookResult:
        """Handle evaluation failure - retry with feedback or halt."""
        max_retries = 2
        if self._retry_count < max_retries:
            self._retry_count += 1
            self._last_eval_failure = reason
            return HookResult.continue_with()
        return HookResult.halt(reason=f"Max retries exceeded. Last failure: {reason}")

    async def _process_output(self, output: SummaryOutput) -> None:
        """Save summary to file and archive source documents."""
        from chimera_core.filesystem.editor import LocalFileEditor

        editor = LocalFileEditor()
        output_dir = Path(self.config.base_path) / self.config.output_directory

        # Generate filename: YYYYMMDD.txt, YYYYMMDD-2.txt, etc.
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{date_str}.txt"
        full_path = output_dir / filename
        counter = 2
        while editor.file_exists(str(full_path)):
            full_path = output_dir / f"{date_str}-{counter}.txt"
            counter += 1

        # Write summary
        content = f"# {output.title}\n\n{output.summary}"
        if output.key_points:
            content += "\n\n## Key Points\n" + "\n".join(f"- {p}" for p in output.key_points)

        editor.write_file(str(full_path), content)

        # Archive source documents
        self._archive_source_documents()

    def _archive_source_documents(self) -> None:
        """Move processed documents to archive directory."""
        input_path = Path(self.config.base_path) / self.config.input_directory
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        for rel_path_str in self._documents.keys():
            src = input_path / rel_path_str
            if src.exists():
                dst = self.archive_dir / rel_path_str
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

    # =========================================================================
    # BlueprintProtocol Serialization
    # =========================================================================

    def _serialize_config(self) -> dict:
        """Serialize space configuration to dict."""
        return {
            "prompt": self.config.prompt,
            "base_path": self.config.base_path,
            "input_directory": self.config.input_directory,
            "output_directory": self.config.output_directory,
            "archive_directory": self.config.archive_directory,
            # Note: evals are not serialized (they're code, not config)
        }

    def to_blueprint_config(self) -> "ComponentConfig":
        """Serialize Space to BlueprintProtocol format with config."""
        from chimera_core.threadprotocol.blueprint import ComponentConfig

        return ComponentConfig(
            class_name=f"chimera_core.spaces.{self.__class__.__name__}",
            version=self.component_version,
            instance_id=self.instance_id or "space",
            config=self._serialize_config(),
        )

    @classmethod
    def from_blueprint_config(cls, space_config: "SpaceConfig") -> "CronSummarizerSpace":
        """Deserialize from BlueprintProtocol format."""
        # Resolve agents using base class helper
        agents = cls._resolve_agents_from_config(space_config)

        if len(agents) != 1:
            raise ValueError(f"CronSummarizerSpace requires exactly 1 agent, got {len(agents)}")

        config = CronSummarizerConfig(
            prompt=space_config.config.get("prompt", ""),
            base_path=space_config.config.get("base_path", ""),
            input_directory=space_config.config.get("input_directory", ""),
            output_directory=space_config.config.get("output_directory", ""),
            archive_directory=space_config.config.get("archive_directory"),
            # Evals loaded from config could be class paths - skip for now
            evals=[],
        )

        space = cls(agents[0], config)
        space.instance_id = "space"
        return space
