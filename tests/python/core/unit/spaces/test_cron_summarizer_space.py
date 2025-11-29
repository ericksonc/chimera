"""Tests for CronSummarizerSpace.

Tests focus on pure functions and isolated logic:
- length_check eval factory
- SummaryOutput model validation
- File type detection
- Retry logic
- Turn decision logic
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from chimera_core.spaces.cron_summarizer_space import (
    AgentEval,
    CronSummarizerConfig,
    CronSummarizerSpace,
    SummaryOutput,
    length_check,
)


class TestLengthCheck:
    """Tests for length_check eval factory."""

    def test_length_check_passes_within_bounds(self):
        """Summary within bounds passes."""
        check = length_check(min_chars=100, max_chars=500)
        output = SummaryOutput(title="Test", summary="x" * 200)

        result = check(output)

        assert result.success is True
        assert result.reason is None

    def test_length_check_fails_too_short(self):
        """Summary below minimum fails with reason."""
        check = length_check(min_chars=100, max_chars=500)
        output = SummaryOutput(title="Test", summary="x" * 50)

        result = check(output)

        assert result.success is False
        assert "too short" in result.reason.lower()
        assert "50" in result.reason
        assert "100" in result.reason

    def test_length_check_fails_too_long(self):
        """Summary above maximum fails with reason."""
        check = length_check(min_chars=100, max_chars=500)
        output = SummaryOutput(title="Test", summary="x" * 600)

        result = check(output)

        assert result.success is False
        assert "too long" in result.reason.lower()
        assert "600" in result.reason
        assert "500" in result.reason

    def test_length_check_exact_minimum(self):
        """Summary at exact minimum passes."""
        check = length_check(min_chars=100, max_chars=500)
        output = SummaryOutput(title="Test", summary="x" * 100)

        result = check(output)

        assert result.success is True

    def test_length_check_exact_maximum(self):
        """Summary at exact maximum passes."""
        check = length_check(min_chars=100, max_chars=500)
        output = SummaryOutput(title="Test", summary="x" * 500)

        result = check(output)

        assert result.success is True

    def test_length_check_default_bounds(self):
        """Default bounds are 500-5000 chars."""
        check = length_check()
        output = SummaryOutput(title="Test", summary="x" * 1000)

        result = check(output)

        assert result.success is True

    def test_length_check_default_fails_below_500(self):
        """Default check fails below 500 chars."""
        check = length_check()
        output = SummaryOutput(title="Test", summary="x" * 400)

        result = check(output)

        assert result.success is False
        assert "500" in result.reason


class TestSummaryOutput:
    """Tests for SummaryOutput model."""

    def test_summary_output_required_fields(self):
        """Title and summary are required."""
        output = SummaryOutput(title="My Title", summary="My summary")

        assert output.title == "My Title"
        assert output.summary == "My summary"
        assert output.key_points is None

    def test_summary_output_with_key_points(self):
        """Key points is optional."""
        output = SummaryOutput(
            title="My Title",
            summary="My summary",
            key_points=["Point 1", "Point 2"],
        )

        assert output.key_points == ["Point 1", "Point 2"]

    def test_summary_output_empty_key_points_list(self):
        """Empty key points list is valid."""
        output = SummaryOutput(
            title="My Title",
            summary="My summary",
            key_points=[],
        )

        assert output.key_points == []


class TestAgentEval:
    """Tests for AgentEval dataclass."""

    def test_agent_eval_success(self):
        """Success eval requires no reason."""
        eval_result = AgentEval(success=True)

        assert eval_result.success is True
        assert eval_result.reason is None

    def test_agent_eval_failure(self):
        """Failure eval includes reason."""
        eval_result = AgentEval(success=False, reason="Summary too short")

        assert eval_result.success is False
        assert eval_result.reason == "Summary too short"


class TestCronSummarizerSpaceFileDetection:
    """Tests for _is_text_file detection."""

    def test_is_text_file_common_extensions(self):
        """Common code/text file extensions are detected."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            text_extensions = [".py", ".js", ".ts", ".md", ".json", ".yaml", ".txt", ".sql"]
            for ext in text_extensions:
                file_path = Path(tmpdir) / f"test{ext}"
                file_path.write_text("content")
                assert space._is_text_file(file_path), f"Expected {ext} to be detected as text"

    def test_is_text_file_common_filenames(self):
        """Common filenames without extensions are detected."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            for filename in ["Dockerfile", "Makefile", "README", "LICENSE"]:
                file_path = Path(tmpdir) / filename
                file_path.write_text("content")
                assert space._is_text_file(file_path), f"Expected {filename} to be detected as text"

    def test_is_text_file_rejects_large_files(self):
        """Files over 1MB are rejected."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            large_file = Path(tmpdir) / "large.txt"
            large_file.write_text("x" * (1_000_001))  # Just over 1MB

            assert space._is_text_file(large_file) is False


class TestCronSummarizerSpaceRetryLogic:
    """Tests for retry logic in _handle_eval_failure."""

    def test_retry_allowed_up_to_max(self):
        """Retries are allowed up to max (2)."""
        from chimera_core.base_plugin import ExecutionControl

        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            # First failure - should continue
            result1 = space._handle_eval_failure("Too short")
            assert result1.control == ExecutionControl.CONTINUE
            assert space._retry_count == 1

            # Second failure - should continue
            result2 = space._handle_eval_failure("Too short")
            assert result2.control == ExecutionControl.CONTINUE
            assert space._retry_count == 2

            # Third failure - should halt
            result3 = space._handle_eval_failure("Too short")
            assert result3.control == ExecutionControl.HALT
            assert "Max retries exceeded" in result3.agent_message

    def test_retry_stores_last_failure(self):
        """Last failure reason is stored for feedback."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            space._handle_eval_failure("Summary too short")

            assert space._last_eval_failure == "Summary too short"


class TestCronSummarizerSpaceTurnDecision:
    """Tests for should_continue_turn decision logic."""

    def test_continue_with_feedback_when_failure_stored(self):
        """Returns continue decision with feedback when failure is stored."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            # Simulate stored failure
            space._last_eval_failure = "Summary too short"

            decision = space.should_continue_turn(None)

            assert decision.decision == "continue"
            assert "Summary too short" in decision.next_prompt
            # Failure should be cleared after returning
            assert space._last_eval_failure is None

    def test_complete_when_no_failure(self):
        """Returns complete decision when no failure stored."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="in",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            decision = space.should_continue_turn(None)

            assert decision.decision == "complete"


class TestCronSummarizerConfig:
    """Tests for CronSummarizerConfig defaults."""

    def test_config_default_archive_directory(self):
        """Archive directory defaults to output_directory/archive."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="inbox",
                output_directory="summaries",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            expected = Path(tmpdir) / "summaries" / "archive"
            assert space.archive_dir == expected

    def test_config_custom_archive_directory(self):
        """Custom archive directory is respected."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="inbox",
                output_directory="summaries",
                archive_directory="custom_archive",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            expected = Path(tmpdir) / "custom_archive"
            assert space.archive_dir == expected

    def test_config_empty_evals_list(self):
        """Evals default to empty list."""
        config = CronSummarizerConfig(
            prompt="test",
            base_path="/tmp",
            input_directory="inbox",
            output_directory="summaries",
        )

        assert config.evals == []


class TestCronSummarizerSpaceDocumentLoading:
    """Tests for load_input_documents."""

    def test_load_documents_formats_correctly(self):
        """Documents are loaded and formatted with headers."""
        with TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "inbox"
            input_dir.mkdir()
            (input_dir / "doc1.txt").write_text("Content 1")
            (input_dir / "doc2.md").write_text("Content 2")

            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="inbox",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            result = space.load_input_documents()

            assert "DOCUMENTS TO SUMMARIZE" in result
            assert "## doc1.txt" in result
            assert "Content 1" in result
            assert "## doc2.md" in result
            assert "Content 2" in result

    def test_load_documents_skips_hidden_files(self):
        """Hidden files (starting with .) are skipped."""
        with TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "inbox"
            input_dir.mkdir()
            (input_dir / "visible.txt").write_text("Visible")
            (input_dir / ".hidden").write_text("Hidden")

            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="inbox",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            result = space.load_input_documents()

            assert "Visible" in result
            assert "Hidden" not in result

    def test_load_documents_empty_directory(self):
        """Returns message when no documents found."""
        with TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "inbox"
            input_dir.mkdir()

            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="inbox",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            result = space.load_input_documents()

            assert "No documents found" in result

    def test_load_documents_nonexistent_directory(self):
        """Returns message when input directory doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            config = CronSummarizerConfig(
                prompt="test",
                base_path=tmpdir,
                input_directory="nonexistent",
                output_directory="out",
            )
            agent = MagicMock()
            space = CronSummarizerSpace(agent, config)

            result = space.load_input_documents()

            assert "does not exist" in result
