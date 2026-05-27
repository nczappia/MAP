"""Unit tests for the Claude Code CLI subprocess wrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from map.tools.claude_code import ClaudeCodeResult, ClaudeCodeRunner


def make_mock_proc(stdout: bytes = b"output\n", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


class TestClaudeCodeResult:
    def test_success_true_on_zero_returncode(self) -> None:
        assert ClaudeCodeResult(stdout="ok", returncode=0).success

    def test_success_false_on_nonzero_returncode(self) -> None:
        assert not ClaudeCodeResult(stdout="err", returncode=1).success


class TestClaudeCodeRunner:
    async def test_run_returns_stdout(self) -> None:
        proc = make_mock_proc(stdout=b"hello from claude\n")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            runner = ClaudeCodeRunner()
            result = await runner.run("do something")

        assert result.stdout == "hello from claude\n"
        assert result.success

    async def test_run_passes_print_flag(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.run("my prompt")

        args = mock_exec.call_args[0]
        assert "claude" in args
        assert "--print" in args
        assert "my prompt" in args

    async def test_run_includes_system_prompt(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.run("prompt", system="you are an expert")

        args = mock_exec.call_args[0]
        assert "--system-prompt" in args
        assert "you are an expert" in args

    async def test_run_merges_default_and_allowed_tools(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner(default_tools=["Read"])
            await runner.run("prompt", allowed_tools=["Edit", "Bash"])

        args = mock_exec.call_args[0]
        tools_idx = list(args).index("--allowedTools")
        tools_str = args[tools_idx + 1]
        assert "Read" in tools_str
        assert "Edit" in tools_str
        assert "Bash" in tools_str

    async def test_run_no_duplicate_tools(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner(default_tools=["Read", "Edit"])
            await runner.run("prompt", allowed_tools=["Edit"])

        args = mock_exec.call_args[0]
        tools_idx = list(args).index("--allowedTools")
        tools_list = args[tools_idx + 1].split(",")
        assert tools_list.count("Edit") == 1

    async def test_run_passes_cwd(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.run("prompt", cwd="/tmp/myrepo")

        kwargs = mock_exec.call_args[1]
        assert kwargs["cwd"] == "/tmp/myrepo"

    async def test_run_timeout_kills_process(self) -> None:
        proc = MagicMock()
        proc.kill = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        # second communicate call after kill
        proc.communicate = AsyncMock(side_effect=[asyncio.TimeoutError, (b"", b"")])

        with (
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            patch("asyncio.wait_for", side_effect=asyncio.TimeoutError),
        ):
            runner = ClaudeCodeRunner()
            with pytest.raises(asyncio.TimeoutError):
                await runner.run("slow task", timeout=0.001)

        proc.kill.assert_called_once()

    async def test_run_without_tools_omits_flag(self) -> None:
        proc = make_mock_proc()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.run("prompt")

        args = mock_exec.call_args[0]
        assert "--allowedTools" not in args
