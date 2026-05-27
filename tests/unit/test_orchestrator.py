"""Unit tests for the supervisor orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from map.agents.base import BaseAgent
from map.comms.base import CommsRouter
from map.session.state import SessionStore
from map.supervisor.orchestrator import Orchestrator, OrchestratorConfig


def make_agent(name: str, output: dict) -> BaseAgent:
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    agent.run = AsyncMock(return_value=output)
    return agent


def make_router(reply: str = "approve") -> CommsRouter:
    router = MagicMock(spec=CommsRouter)
    router.send = AsyncMock()
    router.wait_for_reply = AsyncMock(return_value=reply)
    return router


PLAN_OUTPUT = {
    "summary": "Add login endpoint",
    "steps": [
        {"id": 1, "description": "Create route", "agent": "implementer"},
        {"id": 2, "description": "Write tests", "agent": "tester"},
    ],
}
IMPL_OUTPUT = {"diff": "diff --git a/app.py..."}
REVIEW_OUTPUT = {"passed": True, "comments": []}
TEST_OUTPUT = {"passed": True, "output": "All tests pass"}


@pytest.fixture
async def store(db: aiosqlite.Connection) -> SessionStore:
    return SessionStore(db)


@pytest.fixture
def agents() -> dict:
    return {
        "planner": make_agent("planner", PLAN_OUTPUT),
        "implementer": make_agent("implementer", IMPL_OUTPUT),
        "reviewer": make_agent("reviewer", REVIEW_OUTPUT),
        "tester": make_agent("tester", TEST_OUTPUT),
    }


class TestOrchestrator:
    async def test_run_full_pipeline_succeeds(self, store: SessionStore, agents: dict) -> None:
        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("add login endpoint", "/repo")

        assert session.status == "done"
        assert len(session.subtasks) == 4
        assert all(st.status == "done" for st in session.subtasks)

    async def test_run_sends_plan_checkpoint(self, store: SessionStore, agents: dict) -> None:
        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents=agents)

        await orch.run("task", "/repo")

        # First send should contain "Plan Approval"
        first_message = router.send.call_args_list[0][0][0]
        assert "Plan Approval" in first_message

    async def test_run_sends_commit_checkpoint(self, store: SessionStore, agents: dict) -> None:
        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents=agents)

        await orch.run("task", "/repo")

        last_message = router.send.call_args_list[-1][0][0]
        assert "Commit Approval" in last_message

    async def test_run_rejected_at_plan_sets_failed(
        self, store: SessionStore, agents: dict
    ) -> None:
        router = make_router("reject")
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("task", "/repo")

        assert session.status == "failed"
        # Implementer should never have been called
        agents["implementer"].run.assert_not_awaited()

    async def test_run_checkpoint_timeout_sets_failed(
        self, store: SessionStore, agents: dict
    ) -> None:
        router = make_router.__wrapped__ if hasattr(make_router, "__wrapped__") else None  # type: ignore[attr-defined]
        router = MagicMock(spec=CommsRouter)
        router.send = AsyncMock()
        router.wait_for_reply = AsyncMock(return_value=None)  # timeout
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("task", "/repo")
        assert session.status == "failed"

    async def test_checkpoint_after_review_sends_extra_checkpoint(
        self, store: SessionStore, agents: dict
    ) -> None:
        router = make_router("approve")
        config = OrchestratorConfig(checkpoint_after_review=True)
        orch = Orchestrator(store=store, router=router, agents=agents, config=config)

        await orch.run("task", "/repo")

        messages = [call[0][0] for call in router.send.call_args_list]
        assert any("Review Results" in m for m in messages)

    async def test_failed_review_triggers_checkpoint(
        self, store: SessionStore, agents: dict
    ) -> None:
        agents["reviewer"] = make_agent(
            "reviewer", {"passed": False, "comments": ["missing docstring"]}
        )
        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("task", "/repo")

        messages = [call[0][0] for call in router.send.call_args_list]
        assert any("Review Results" in m for m in messages)
        assert session.status == "done"

    async def test_missing_agent_raises(self, store: SessionStore) -> None:
        router = make_router("approve")
        orch = Orchestrator(
            store=store,
            router=router,
            agents={"planner": make_agent("planner", PLAN_OUTPUT)},
        )
        with pytest.raises(ValueError, match="implementer"):
            await orch.run("task", "/repo")

    async def test_resume_reloads_paused_session(self, store: SessionStore, agents: dict) -> None:
        from map.session.state import Checkpoint, Session, Subtask, Task  # noqa: F811

        task = Task(description="my task", repo_path="/repo")
        session = Session(task=task, status="paused_at_checkpoint")
        await store.save_session(session)

        # Simulate: planner already ran and returned a plan
        planner_st = Subtask(
            session_id=session.id,
            agent="planner",
            input={"description": "my task", "repo_path": "/repo"},
            output=PLAN_OUTPUT,
            status="done",
        )
        session.subtasks.append(planner_st)
        await store.save_subtask(planner_st)

        # plan_approval checkpoint is pending (process died before user replied)
        cp = Checkpoint(
            session_id=session.id,
            type="plan_approval",
            message="approve?",
        )
        session.checkpoints.append(cp)
        await store.save_checkpoint(cp)

        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents=agents)

        resumed = await orch.resume(session.id)

        # Planner should NOT run again
        agents["planner"].run.assert_not_awaited()
        assert resumed.status == "done"

    async def test_resume_nonexistent_session_raises(self, store: SessionStore) -> None:
        router = make_router("approve")
        orch = Orchestrator(store=store, router=router, agents={})
        with pytest.raises(ValueError, match="not found"):
            await orch.resume("nonexistent-id")
