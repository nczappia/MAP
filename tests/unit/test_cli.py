"""Unit tests for CLI commands (typer CliRunner, no real API calls)."""

from __future__ import annotations

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

    def test_run_fails_without_api_key(self) -> None:
        import os
        from unittest.mock import patch

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["run", "add a feature", "--repo", "/tmp"])
        # Should exit with an error mentioning the API key
        assert result.exit_code != 0 or "ANTHROPIC_API_KEY" in result.output
