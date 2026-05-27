"""Decomposes a free-text task into an initial planner subtask."""

from __future__ import annotations

from map.session.state import Session, Subtask


def build_planner_subtask(session: Session) -> Subtask:
    """Create the first subtask: ask the planner to produce a structured plan."""
    subtask = Subtask(
        session_id=session.id,
        agent="planner",
        input={
            "description": session.task.description,
            "repo_path": session.task.repo_path,
        },
    )
    session.subtasks.append(subtask)
    return subtask
