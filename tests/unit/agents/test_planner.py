"""Unit tests for PlannerAgent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from map.agents.planner import PlannerAgent
from map.session.state import Session, Subtask, Task


def make_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text=response_text)])
    )
    return client


def make_subtask(
    description: str = "add a login endpoint",
    repo: str = "/repo",
    context: str | None = None,
) -> Subtask:
    inp: dict[str, str] = {"description": description, "repo_path": repo}
    if context:
        inp["context"] = context
    return Subtask(session_id="s1", agent="planner", input=inp)


def make_session() -> Session:
    return Session(task=Task(description="add login", repo_path="/repo"))


VALID_PLAN = json.dumps(
    {
        "summary": "Add a login endpoint to the API",
        "steps": [
            {"id": 1, "description": "Create POST /login route", "agent": "implementer"},
            {"id": 2, "description": "Write tests for login", "agent": "tester"},
            {"id": 3, "description": "Review implementation", "agent": "reviewer"},
        ],
    }
)


class TestPlannerAgent:
    def test_name(self) -> None:
        agent = PlannerAgent(client=MagicMock())
        assert agent.name == "planner"

    async def test_run_returns_parsed_plan(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client)

        result = await agent.run(make_subtask(), make_session())

        assert "summary" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) == 3

    async def test_run_passes_task_description_to_api(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client)

        await agent.run(make_subtask("build a caching layer"), make_session())

        call_kwargs = client.messages.create.call_args[1]
        user_message = call_kwargs["messages"][0]["content"]
        assert "build a caching layer" in user_message

    async def test_run_passes_repo_path_to_api(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client)

        await agent.run(make_subtask(repo="/my/project"), make_session())

        call_kwargs = client.messages.create.call_args[1]
        user_message = call_kwargs["messages"][0]["content"]
        assert "/my/project" in user_message

    async def test_run_raises_on_invalid_json(self) -> None:
        client = make_client("not json at all")
        agent = PlannerAgent(client=client)

        with pytest.raises(ValueError, match="non-JSON"):
            await agent.run(make_subtask(), make_session())

    async def test_run_raises_when_steps_missing(self) -> None:
        client = make_client(json.dumps({"summary": "ok"}))
        agent = PlannerAgent(client=client)

        with pytest.raises(ValueError, match="steps"):
            await agent.run(make_subtask(), make_session())

    async def test_run_uses_configured_model(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client, model="claude-opus-4-7")

        await agent.run(make_subtask(), make_session())

        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"

    async def test_context_included_in_prompt(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client)

        await agent.run(make_subtask(context="Use FastAPI, no new deps."), make_session())

        call_kwargs = client.messages.create.call_args[1]
        user_message = call_kwargs["messages"][0]["content"]
        assert "Use FastAPI, no new deps." in user_message

    async def test_no_context_key_omitted_from_prompt(self) -> None:
        client = make_client(VALID_PLAN)
        agent = PlannerAgent(client=client)

        await agent.run(make_subtask(), make_session())

        call_kwargs = client.messages.create.call_args[1]
        user_message = call_kwargs["messages"][0]["content"]
        assert "Additional context" not in user_message
