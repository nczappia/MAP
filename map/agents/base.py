"""Abstract base agent and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from map.session.state import Session, Subtask


class BaseAgent(ABC):
    """All agents implement this interface.

    Agents are stateless per invocation; all persistent state lives in Session.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier used to label subtasks (e.g. 'planner')."""
        ...

    @abstractmethod
    async def run(self, subtask: Subtask, session: Session) -> dict[str, Any]:
        """Execute the subtask and return an output dict.

        The returned dict is stored on subtask.output by the caller.
        Raise on unrecoverable errors; the orchestrator will mark the subtask failed.
        """
        ...
