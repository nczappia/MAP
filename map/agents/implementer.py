"""ImplementerAgent: runs Claude Code CLI to apply code changes."""

from __future__ import annotations

from typing import Any

from map.agents.base import BaseAgent
from map.session.state import Session, Subtask
from map.tools.claude_code import ClaudeCodeRunner

_SYSTEM = """\
You are a senior software engineer implementing a coding task.
You have access to file editing tools. Make the minimal, correct changes needed.
After completing all edits, output a brief summary of what you changed.
"""


class ImplementerAgent(BaseAgent):
    """Uses Claude Code CLI subprocess to edit files in the target repository."""

    def __init__(self, runner: ClaudeCodeRunner, tools: list[str] | None = None) -> None:
        self._runner = runner
        self._tools = tools or ["Edit", "Write", "Bash", "Read"]

    @property
    def name(self) -> str:
        return "implementer"

    async def run(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        plan = subtask.input.get("plan", {})
        repo_path = subtask.input.get("repo_path", ".")

        steps_text = "\n".join(
            f"  {s.get('id', '?')}. {s.get('description', '')}"
            for s in plan.get("steps", [])
            if s.get("agent") == "implementer"
        )
        prompt = (
            f"Implement the following plan in the repository at {repo_path}:\n\n"
            f"Summary: {plan.get('summary', '')}\n\n"
            f"Steps to implement:\n{steps_text or 'See plan summary above.'}"
        )

        result = await self._runner.run(
            prompt,
            cwd=repo_path,
            system=_SYSTEM,
            allowed_tools=self._tools,
        )

        return {
            "success": result.success,
            "output": result.stdout,
            "diff": result.stdout[:2000],
        }
