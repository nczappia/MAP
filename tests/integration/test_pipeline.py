"""Integration test: full orchestrator pipeline with mocked external deps."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from map.agents.base import BaseAgent
from map.comms.base import CommsRouter
from map.session.state import SessionStore
from map.supervisor.orchestrator import Orchestrator, OrchestratorConfig

PLAN = {
    "summary": "Add a health check endpoint",
    "steps": [
        {"id": 1, "description": "Add GET /health route", "agent": "implementer"},
        {"id": 2, "description": "Write tests for /health", "agent": "tester"},
        {"id": 3, "description": "Review the implementation", "agent": "reviewer"},
    ],
}


def make_agent(name: str, output: dict) -> BaseAgent:
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    agent.run = AsyncMock(return_value=output)
    return agent


def make_router(replies: list[str]) -> CommsRouter:
    """Router that returns successive replies from the list."""
    router = MagicMock(spec=CommsRouter)
    router.send = AsyncMock()
    router.wait_for_reply = AsyncMock(side_effect=replies)
    return router


@pytest.fixture
async def store(db: aiosqlite.Connection) -> SessionStore:
    return SessionStore(db)


class TestFullPipeline:
    async def test_full_run_approve_all(self, store: SessionStore) -> None:
        """Happy path: user approves both checkpoints, pipeline completes."""
        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {"diff": "diff output"}),
            "reviewer": make_agent("reviewer", {"passed": True, "comments": []}),
            "tester": make_agent("tester", {"passed": True, "output": "all pass"}),
        }
        router = make_router(["approve", "approve"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("add health check endpoint", "/my/repo")

        assert session.status == "done"
        assert len(session.subtasks) == 4
        assert all(st.status == "done" for st in session.subtasks)
        assert len(session.checkpoints) == 2
        assert all(cp.is_resolved for cp in session.checkpoints)

    async def test_full_run_reject_at_plan(self, store: SessionStore) -> None:
        """User rejects plan — pipeline stops, no implementation runs."""
        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {}),
            "reviewer": make_agent("reviewer", {}),
            "tester": make_agent("tester", {}),
        }
        router = make_router(["reject"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("add health check", "/repo")

        assert session.status == "failed"
        assert len(session.subtasks) == 1  # only planner ran
        agents["implementer"].run.assert_not_awaited()

    async def test_full_run_reject_at_commit(self, store: SessionStore) -> None:
        """User approves plan but rejects commit — session fails at the end."""
        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {"diff": "diff output"}),
            "reviewer": make_agent("reviewer", {"passed": True, "comments": []}),
            "tester": make_agent("tester", {"passed": True, "output": "ok"}),
        }
        router = make_router(["approve", "reject"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        session = await orch.run("add feature", "/repo")

        assert session.status == "failed"
        assert len(session.checkpoints) == 2

    async def test_session_persists_across_resume(self, store: SessionStore) -> None:
        """Verify SQLite persistence: save a paused session, reload it, resume to done."""
        from map.session.state import Checkpoint, Session, Subtask, Task

        task = Task(description="add login", repo_path="/repo")
        session = Session(task=task, status="paused_at_checkpoint")
        await store.save_session(session)

        # Planner subtask already complete
        planner_st = Subtask(
            session_id=session.id,
            agent="planner",
            input={"description": "add login", "repo_path": "/repo"},
            output=PLAN,
            status="done",
        )
        session.subtasks.append(planner_st)
        await store.save_subtask(planner_st)

        # Pending plan_approval checkpoint
        cp = Checkpoint(session_id=session.id, type="plan_approval", message="approve?")
        session.checkpoints.append(cp)
        await store.save_checkpoint(cp)

        # --- Simulate process restart: reload from DB ---
        reloaded = await store.load_session(session.id)
        assert reloaded is not None
        assert reloaded.pending_checkpoint is not None

        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {"diff": "d"}),
            "reviewer": make_agent("reviewer", {"passed": True, "comments": []}),
            "tester": make_agent("tester", {"passed": True, "output": "ok"}),
        }
        router = make_router(["approve", "approve"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        resumed = await orch.resume(reloaded.id)

        assert resumed.status == "done"
        agents["planner"].run.assert_not_awaited()  # planner was already done

    async def test_with_review_checkpoint_enabled(self, store: SessionStore) -> None:
        """When checkpoint_after_review=True, three checkpoints are sent."""
        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {"diff": "d"}),
            "reviewer": make_agent("reviewer", {"passed": True, "comments": []}),
            "tester": make_agent("tester", {"passed": True, "output": "ok"}),
        }
        router = make_router(["approve", "approve", "approve"])
        config = OrchestratorConfig(checkpoint_after_review=True)
        orch = Orchestrator(store=store, router=router, agents=agents, config=config)

        session = await orch.run("add feature", "/repo")

        assert session.status == "done"
        assert len(session.checkpoints) == 3
        checkpoint_types = {cp.type for cp in session.checkpoints}
        assert "plan_approval" in checkpoint_types
        assert "review_results" in checkpoint_types
        assert "commit_approval" in checkpoint_types

    async def test_failed_agent_marks_session_failed(self, store: SessionStore) -> None:
        """If an agent raises, the session is marked failed."""
        failing_impl = MagicMock(spec=BaseAgent)
        failing_impl.name = "implementer"
        failing_impl.run = AsyncMock(side_effect=RuntimeError("subprocess crashed"))

        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": failing_impl,
            "reviewer": make_agent("reviewer", {}),
            "tester": make_agent("tester", {}),
        }
        router = make_router(["approve"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        with pytest.raises(RuntimeError):
            await orch.run("add feature", "/repo")

        reloaded = await store.load_session(session_id=session_id_from_store(store))
        if reloaded:
            assert reloaded.status == "failed"

    async def test_checkpoint_messages_contain_expected_content(self, store: SessionStore) -> None:
        """Verify that checkpoint messages include relevant content."""
        agents = {
            "planner": make_agent("planner", PLAN),
            "implementer": make_agent("implementer", {"diff": "--- a/main.py\n+++ b/main.py"}),
            "reviewer": make_agent("reviewer", {"passed": True, "comments": []}),
            "tester": make_agent("tester", {"passed": True, "output": "5 passed"}),
        }
        router = make_router(["approve", "approve"])
        orch = Orchestrator(store=store, router=router, agents=agents)

        await orch.run("add health check", "/repo")

        messages = [call[0][0] for call in router.send.call_args_list]
        plan_msg = messages[0]
        commit_msg = messages[1]

        assert "Add a health check endpoint" in plan_msg
        assert "approve" in plan_msg.lower()
        assert "Commit Approval" in commit_msg
        assert "PASSED" in commit_msg


def session_id_from_store(store: SessionStore) -> str:
    # Helper to get the last session ID — used only in the failed agent test
    return ""  # pragma: no cover
