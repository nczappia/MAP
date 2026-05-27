"""Unit tests for ReviewerAgent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from map.agents.reviewer import ReviewerAgent
from map.session.state import Session, Subtask, Task


def make_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text=response_text)])
    )
    return client


def make_subtask(impl_output: str = "added login route", diff: str = "+def login()") -> Subtask:
    return Subtask(
        session_id="s1",
        agent="reviewer",
        input={"impl": {"output": impl_output, "diff": diff}, "repo_path": "/repo"},
    )


def make_session() -> Session:
    return Session(task=Task(description="add login", repo_path="/repo"))


PASS_RESPONSE = json.dumps({"passed": True, "comments": []})
FAIL_RESPONSE = json.dumps({"passed": False, "comments": ["missing error handling"]})


class TestReviewerAgent:
    def test_name(self) -> None:
        assert ReviewerAgent(client=MagicMock()).name == "reviewer"

    async def test_run_returns_passed_true(self) -> None:
        client = make_client(PASS_RESPONSE)
        agent = ReviewerAgent(client=client)

        result = await agent.run(make_subtask(), make_session())

        assert result["passed"] is True
        assert result["comments"] == []

    async def test_run_returns_passed_false_with_comments(self) -> None:
        client = make_client(FAIL_RESPONSE)
        agent = ReviewerAgent(client=client)

        result = await agent.run(make_subtask(), make_session())

        assert result["passed"] is False
        assert "missing error handling" in result["comments"]

    async def test_run_includes_impl_output_in_prompt(self) -> None:
        client = make_client(PASS_RESPONSE)
        agent = ReviewerAgent(client=client)

        await agent.run(make_subtask(impl_output="added POST /login"), make_session())

        call_kwargs = client.messages.create.call_args[1]
        user_content = call_kwargs["messages"][0]["content"]
        assert "added POST /login" in user_content

    async def test_run_raises_on_invalid_json(self) -> None:
        client = make_client("not json")
        agent = ReviewerAgent(client=client)

        with pytest.raises(ValueError, match="non-JSON"):
            await agent.run(make_subtask(), make_session())

    async def test_run_raises_when_passed_missing(self) -> None:
        client = make_client(json.dumps({"comments": []}))
        agent = ReviewerAgent(client=client)

        with pytest.raises(ValueError, match="passed"):
            await agent.run(make_subtask(), make_session())

    async def test_run_uses_configured_model(self) -> None:
        client = make_client(PASS_RESPONSE)
        agent = ReviewerAgent(client=client, model="claude-opus-4-7")

        await agent.run(make_subtask(), make_session())

        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"
