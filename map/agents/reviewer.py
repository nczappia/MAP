"""ReviewerAgent: reviews implementation output using the Anthropic SDK."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from map.agents.base import BaseAgent
from map.session.state import Session, Subtask

_SYSTEM = """\
You are a senior software engineer performing a code review.
You will be given a description of what was implemented and any diff or output from the implementer.

Respond with valid JSON only — no prose, no markdown fences. Format:
{
  "passed": true,
  "comments": ["<specific comment>", ...]
}

Be concise. Flag real issues (bugs, security, missing tests). Minor style is not a blocker.
If the implementation looks correct and complete, return passed: true with an empty comments list.
"""


class ReviewerAgent(BaseAgent):
    """Uses the Anthropic SDK to review implementation output."""

    def __init__(self, client: anthropic.AsyncAnthropic, model: str = "claude-sonnet-4-6") -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "reviewer"

    async def run(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        impl = subtask.input.get("impl", {})
        repo_path = subtask.input.get("repo_path", ".")

        prompt = (
            f"Review the following implementation in repository {repo_path}:\n\n"
            f"Implementation output:\n{impl.get('output', 'N/A')[:3000]}\n\n"
            f"Diff:\n{impl.get('diff', 'N/A')[:3000]}"
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        try:
            review = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Reviewer returned non-JSON: {raw!r}") from exc

        if "passed" not in review:
            raise ValueError(f"Reviewer response missing 'passed' field: {review}")

        return review
