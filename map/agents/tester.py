"""TesterAgent: runs tests via Claude Code CLI and reports results."""

from __future__ import annotations

from typing import Any

from map.agents.base import BaseAgent
from map.session.state import Session, Subtask
from map.tools.claude_code import ClaudeCodeRunner

_SYSTEM = """\
You are a QA engineer. Your job is to run the existing test suite and report results.
Run the tests using the appropriate test runner for this project (pytest, npm test, etc.).
Output the raw test results followed by a one-line summary: PASSED or FAILED.
"""

_PROMPT = """\
Run the tests for the project at {repo_path}.
Detect the test runner automatically (look for pytest.ini, pyproject.toml, package.json, etc.).
Report the full output and end with a line: TESTS PASSED or TESTS FAILED.
"""


class TesterAgent(BaseAgent):
    """Uses Claude Code CLI subprocess to run the project test suite."""

    def __init__(self, runner: ClaudeCodeRunner, tools: list[str] | None = None) -> None:
        self._runner = runner
        self._tools = tools or ["Bash", "Read"]

    @property
    def name(self) -> str:
        return "tester"

    async def run(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        repo_path = subtask.input.get("repo_path", ".")
        prompt = _PROMPT.format(repo_path=repo_path)

        result = await self._runner.run(
            prompt,
            cwd=repo_path,
            system=_SYSTEM,
            allowed_tools=self._tools,
        )

        output = result.stdout
        passed = "TESTS PASSED" in output or (result.success and "TESTS FAILED" not in output)

        return {
            "passed": passed,
            "output": output[:3000],
            "returncode": result.returncode,
        }
