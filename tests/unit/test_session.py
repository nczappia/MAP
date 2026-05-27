"""Unit tests for session state and SQLite persistence."""

from __future__ import annotations

import aiosqlite
import pytest

from map.session.state import Checkpoint, Session, SessionStore, Subtask, Task


@pytest.fixture
async def store(db: aiosqlite.Connection) -> SessionStore:
    return SessionStore(db)


def make_session(description: str = "add tests", repo: str = "/tmp/repo") -> Session:
    return Session(task=Task(description=description, repo_path=repo))


class TestTask:
    def test_defaults_set_id_and_timestamp(self) -> None:
        t = Task(description="fix bug", repo_path="/repo")
        assert t.id
        assert t.created_at is not None


class TestSubtask:
    def test_defaults(self) -> None:
        st = Subtask(session_id="s1", agent="planner", input={"task": "plan it"})
        assert st.status == "pending"
        assert st.output is None


class TestCheckpoint:
    def test_is_resolved_false_when_no_response(self) -> None:
        cp = Checkpoint(session_id="s1", type="plan_approval", message="approve?")
        assert not cp.is_resolved

    def test_is_resolved_true_when_response_set(self) -> None:
        cp = Checkpoint(session_id="s1", type="plan_approval", message="approve?", response="yes")
        assert cp.is_resolved


class TestSession:
    def test_pending_checkpoint_returns_first_unresolved(self) -> None:
        session = make_session()
        resolved = Checkpoint(
            session_id=session.id,
            type="plan_approval",
            message="ok?",
            response="yes",
        )
        pending = Checkpoint(session_id=session.id, type="commit_approval", message="commit?")
        session.checkpoints = [resolved, pending]
        assert session.pending_checkpoint is pending

    def test_pending_checkpoint_none_when_all_resolved(self) -> None:
        session = make_session()
        cp = Checkpoint(session_id=session.id, type="plan_approval", message="ok?", response="yes")
        session.checkpoints = [cp]
        assert session.pending_checkpoint is None


class TestSessionStore:
    async def test_save_and_load_session(self, store: SessionStore) -> None:
        session = make_session()
        await store.save_session(session)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.task.description == "add tests"
        assert loaded.status == "running"

    async def test_load_nonexistent_returns_none(self, store: SessionStore) -> None:
        result = await store.load_session("does-not-exist")
        assert result is None

    async def test_update_session_status(self, store: SessionStore) -> None:
        session = make_session()
        await store.save_session(session)

        session.status = "done"
        await store.save_session(session)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert loaded.status == "done"

    async def test_save_and_load_subtask(self, store: SessionStore) -> None:
        session = make_session()
        await store.save_session(session)

        st = Subtask(session_id=session.id, agent="planner", input={"desc": "plan it"})
        session.subtasks.append(st)
        await store.save_subtask(st)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert len(loaded.subtasks) == 1
        assert loaded.subtasks[0].agent == "planner"
        assert loaded.subtasks[0].status == "pending"

    async def test_update_subtask_output(self, store: SessionStore) -> None:
        session = make_session()
        await store.save_session(session)

        st = Subtask(session_id=session.id, agent="planner", input={})
        await store.save_subtask(st)

        st.output = {"steps": ["step1", "step2"]}
        st.status = "done"
        await store.save_subtask(st)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert loaded.subtasks[0].output == {"steps": ["step1", "step2"]}
        assert loaded.subtasks[0].status == "done"

    async def test_save_and_load_checkpoint(self, store: SessionStore) -> None:
        session = make_session()
        await store.save_session(session)

        cp = Checkpoint(session_id=session.id, type="plan_approval", message="approve the plan?")
        session.checkpoints.append(cp)
        await store.save_checkpoint(cp)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert len(loaded.checkpoints) == 1
        assert loaded.checkpoints[0].type == "plan_approval"
        assert not loaded.checkpoints[0].is_resolved

    async def test_resolve_checkpoint_persists(self, store: SessionStore) -> None:
        from datetime import datetime, timezone

        session = make_session()
        await store.save_session(session)

        cp = Checkpoint(session_id=session.id, type="commit_approval", message="commit?")
        await store.save_checkpoint(cp)

        cp.response = "approve"
        cp.resolved_at = datetime.now(timezone.utc)
        await store.save_checkpoint(cp)

        loaded = await store.load_session(session.id)
        assert loaded is not None
        assert loaded.checkpoints[0].response == "approve"
        assert loaded.checkpoints[0].is_resolved

    async def test_list_sessions(self, store: SessionStore) -> None:
        s1 = make_session("task one")
        s2 = make_session("task two")
        await store.save_session(s1)
        await store.save_session(s2)

        sessions = await store.list_sessions()
        assert len(sessions) == 2

    async def test_session_resume_has_pending_checkpoint(self, store: SessionStore) -> None:
        """Simulates a pipeline interrupted mid-checkpoint: reload finds the pending checkpoint."""
        session = make_session()
        await store.save_session(session)

        cp = Checkpoint(session_id=session.id, type="plan_approval", message="approve?")
        await store.save_checkpoint(cp)
        session.status = "paused_at_checkpoint"
        await store.save_session(session)

        reloaded = await store.load_session(session.id)
        assert reloaded is not None
        assert reloaded.status == "paused_at_checkpoint"
        assert reloaded.pending_checkpoint is not None
        assert reloaded.pending_checkpoint.type == "plan_approval"
