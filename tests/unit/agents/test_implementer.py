"""Unit tests for ImplementerAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from map.agents.implementer import ImplementerAgent
from map.session.state import Session, Subtask, Task
from map.tools.claude_code import ClaudeCodeResult, ClaudeCodeRunner


def make_runner(output: str = "edited file.py", success: bool = True) -> ClaudeCodeRunner:
    runner = MagicMock(spec=ClaudeCodeRunner)
    rc = 0 if success else 1
    runner.run = AsyncMock(return_value=ClaudeCodeResult(stdout=output, returncode=rc))
    return runner


def make_subtask(plan: dict | None = None, repo: str = "/repo") -> Subtask:
    return Subtask(
        session_id="s1",
        agent="implementer",
        input={
            "plan": plan
            or {
                "summary": "add hello",
                "steps": [{"id": 1, "description": "add hello function", "agent": "implementer"}],
            },
            "repo_path": repo,
        },
    )


def make_session() -> Session:
    return Session(task=Task(description="add hello", repo_path="/repo"))


class TestImplementerAgent:
    def test_name(self) -> None:
        agent = ImplementerAgent(runner=MagicMock())
        assert agent.name == "implementer"

    async def test_run_returns_success_dict(self) -> None:
        runner = make_runner("edited main.py\n")
        agent = ImplementerAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert result["success"] is True
        assert "output" in result
        assert "diff" in result

    async def test_run_passes_repo_path_as_cwd(self) -> None:
        runner = make_runner()
        agent = ImplementerAgent(runner=runner)

        await agent.run(make_subtask(repo="/my/project"), make_session())

        call_kwargs = runner.run.call_args[1]
        assert call_kwargs["cwd"] == "/my/project"

    async def test_run_includes_plan_summary_in_prompt(self) -> None:
        runner = make_runner()
        agent = ImplementerAgent(runner=runner)

        await agent.run(make_subtask(), make_session())

        prompt = runner.run.call_args[0][0]
        assert "add hello" in prompt

    async def test_run_only_includes_implementer_steps(self) -> None:
        plan = {
            "summary": "add auth",
            "steps": [
                {"id": 1, "description": "create route", "agent": "implementer"},
                {"id": 2, "description": "write tests", "agent": "tester"},
            ],
        }
        runner = make_runner()
        agent = ImplementerAgent(runner=runner)

        await agent.run(make_subtask(plan=plan), make_session())

        prompt = runner.run.call_args[0][0]
        assert "create route" in prompt
        assert "write tests" not in prompt

    async def test_run_failure_still_returns_dict(self) -> None:
        runner = make_runner(success=False)
        agent = ImplementerAgent(runner=runner)

        result = await agent.run(make_subtask(), make_session())

        assert result["success"] is False

    async def test_run_passes_allowed_tools(self) -> None:
        runner = make_runner()
        tools = ["Edit", "Write"]
        agent = ImplementerAgent(runner=runner, tools=tools)

        await agent.run(make_subtask(), make_session())

        call_kwargs = runner.run.call_args[1]
        assert call_kwargs["allowed_tools"] == tools
