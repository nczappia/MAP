"""PlannerAgent: decomposes a task description into an ordered list of steps."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from map.agents.base import BaseAgent
from map.session.state import Session, Subtask

_SYSTEM = """\
You are a senior software engineer acting as a planning agent.
Given a coding task description and the target repository path, produce a clear, ordered plan.

Respond with valid JSON only — no prose, no markdown fences. Format:
{
  "summary": "<one sentence describing the overall goal>",
  "steps": [
    {"id": 1, "description": "<what to do>", "agent": "implementer"},
    ...
  ]
}

Allowed agent values: "implementer", "reviewer", "tester".
Keep steps concrete and actionable. Aim for 3-7 steps.
"""


class PlannerAgent(BaseAgent):
    """Uses the Anthropic SDK to produce a structured implementation plan."""

    def __init__(self, client: anthropic.AsyncAnthropic, model: str = "claude-sonnet-4-6") -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "planner"

    async def run(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        prompt = (
            f"Task: {subtask.input['description']}\n"
            f"Repository: {subtask.input.get('repo_path', 'unknown')}"
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Planner returned non-JSON response: {raw!r}") from exc

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError(f"Planner response missing 'steps' list: {plan}")

        return plan
