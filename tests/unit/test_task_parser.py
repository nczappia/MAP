"""Unit tests for task_parser."""

from __future__ import annotations

from map.session.state import Session, Task
from map.supervisor.task_parser import build_planner_subtask


def make_session() -> Session:
    return Session(task=Task(description="add tests", repo_path="/repo"))


class TestBuildPlannerSubtask:
    def test_creates_subtask_with_planner_agent(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert st.agent == "planner"

    def test_subtask_input_contains_description(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert st.input["description"] == "add tests"

    def test_subtask_input_contains_repo_path(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert st.input["repo_path"] == "/repo"

    def test_subtask_appended_to_session(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert st in session.subtasks

    def test_subtask_linked_to_session_id(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert st.session_id == session.id

    def test_context_included_in_input_when_provided(self) -> None:
        session = make_session()
        st = build_planner_subtask(session, context="Use FastAPI, no new deps.")
        assert st.input["context"] == "Use FastAPI, no new deps."

    def test_context_absent_when_not_provided(self) -> None:
        session = make_session()
        st = build_planner_subtask(session)
        assert "context" not in st.input

    def test_context_absent_when_empty_string(self) -> None:
        session = make_session()
        st = build_planner_subtask(session, context="")
        assert "context" not in st.input
