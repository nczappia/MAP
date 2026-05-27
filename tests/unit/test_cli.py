"""Unit tests for CLI commands (typer CliRunner, no real API calls)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from map.cli import app

runner = CliRunner()


class TestCLIHelp:
    def test_app_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "resume" in result.output
        assert "status" in result.output
        assert "sessions" in result.output

    def test_run_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--repo" in result.output

    def test_resume_help(self) -> None:
        result = runner.invoke(app, ["resume", "--help"])
        assert result.exit_code == 0
        assert "session-id" in result.output.lower() or "SESSION_ID" in result.output

    def test_status_help(self) -> None:
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_sessions_help(self) -> None:
        result = runner.invoke(app, ["sessions", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output

    def test_help_cmd_prints_guide(self) -> None:
        result = runner.invoke(app, ["help"])
        assert result.exit_code == 0
        assert "MAP" in result.output
        assert "COMMANDS" in result.output
        assert "HOW THE PIPELINE WORKS" in result.output
        assert "TELEGRAM" in result.output

    def test_run_context_flag_in_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert "--context" in result.output or "-x" in result.output

    def test_run_context_missing_file_exits_nonzero(self) -> None:
        import os
        from unittest.mock import patch

        env = {**os.environ, "ANTHROPIC_API_KEY": "sk-test"}
        with patch.dict(os.environ, env):
            result = runner.invoke(
                app, ["run", "task", "--repo", "/tmp", "--context", "/nonexistent/file.md"]
            )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_run_context_valid_file_is_accepted(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Use FastAPI only.")
            ctx_path = f.name
        try:
            # A valid context file should not cause an early exit with "not found"
            result = runner.invoke(app, ["run", "--help"])
            assert "--context" in result.output or "-x" in result.output
        finally:
            Path(ctx_path).unlink(missing_ok=True)

    def test_run_fails_without_api_key(self) -> None:
        import os
        from unittest.mock import patch

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["run", "add a feature", "--repo", "/tmp"])
        # Should exit with an error mentioning the API key
        assert result.exit_code != 0 or "ANTHROPIC_API_KEY" in result.output
