"""Unit tests for TesterAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from map.agents.tester import TesterAgent
from map.session.state import Session, Subtask, Task
from map.tools.claude_code import ClaudeCodeResult, ClaudeCodeRunner


def make_runner(output: str, returncode: int = 0) -> ClaudeCodeRunner:
    runner = MagicMock(spec=ClaudeCodeRunner)
    runner.run = AsyncMock(return_value=ClaudeCodeResult(stdout=output, returncode=returncode))
    return runner


def make_subtask(repo: str = "/repo") -> Subtask:
    return Subtask(session_id="s1", agent="tester", input={"repo_path": repo})


def make_session() -> Session:
    return Session(task=Task(description="add tests", repo_path="/repo"))


class TestTesterAgent:
    def test_name(self) -> None:
        assert TesterAgent(runner=MagicMock()).name == "tester"

    async def test_run_passed_when_tests_pass_keyword(self) -> None:
        runner = make_runner("5 passed in 0.1s\nTESTS PASSED")
        agent = TesterAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert result["passed"] is True

    async def test_run_failed_when_tests_fail_keyword(self) -> None:
        runner = make_runner("2 failed\nTESTS FAILED", returncode=1)
        agent = TesterAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert result["passed"] is False

    async def test_run_passed_on_zero_returncode_without_keyword(self) -> None:
        runner = make_runner("all good", returncode=0)
        agent = TesterAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert result["passed"] is True

    async def test_run_includes_output_in_result(self) -> None:
        runner = make_runner("test output here\nTESTS PASSED")
        agent = TesterAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert "test output here" in result["output"]

    async def test_run_passes_repo_as_cwd(self) -> None:
        runner = make_runner("TESTS PASSED")
        agent = TesterAgent(runner=runner)

        await agent.run(make_subtask(repo="/custom/path"), make_session())

        call_kwargs = runner.run.call_args[1]
        assert call_kwargs["cwd"] == "/custom/path"

    async def test_run_passes_tools(self) -> None:
        runner = make_runner("TESTS PASSED")
        agent = TesterAgent(runner=runner, tools=["Bash"])

        await agent.run(make_subtask(), make_session())

        call_kwargs = runner.run.call_args[1]
        assert call_kwargs["allowed_tools"] == ["Bash"]

    async def test_run_truncates_long_output(self) -> None:
        long_output = "x" * 5000 + "\nTESTS PASSED"
        runner = make_runner(long_output)
        agent = TesterAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert len(result["output"]) <= 3000
