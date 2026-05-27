"""Session state: data model and SQLite persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


@dataclass
class Task:
    description: str
    repo_path: str
    id: str = field(default_factory=_uid)
    created_at: datetime = field(default_factory=_now)


@dataclass
class Subtask:
    session_id: str
    agent: str  # "planner" | "implementer" | "reviewer" | "tester"
    input: dict[str, Any]
    id: str = field(default_factory=_uid)
    output: dict[str, Any] | None = None
    status: str = "pending"  # "pending" | "running" | "done" | "failed"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class Checkpoint:
    session_id: str
    type: str  # "plan_approval" | "review_results" | "commit_approval"
    message: str
    id: str = field(default_factory=_uid)
    response: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)

    @property
    def is_resolved(self) -> bool:
        return self.response is not None


@dataclass
class Session:
    task: Task
    id: str = field(default_factory=_uid)
    status: str = "running"  # "running" | "paused_at_checkpoint" | "done" | "failed"
    subtasks: list[Subtask] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    @property
    def pending_checkpoint(self) -> Checkpoint | None:
        for cp in self.checkpoints:
            if not cp.is_resolved:
                return cp
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    task_description TEXT NOT NULL,
    task_repo_path TEXT NOT NULL,
    task_created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    response TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);
"""


class SessionStore:
    """Async SQLite-backed session persistence."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    @staticmethod
    async def apply_schema(db: aiosqlite.Connection) -> None:
        await db.executescript(_SCHEMA)
        await db.commit()

    @classmethod
    async def open(cls, db_path: str) -> SessionStore:
        db = await aiosqlite.connect(db_path)
        await cls.apply_schema(db)
        return cls(db)

    async def close(self) -> None:
        await self._db.close()

    # --- Session ---

    async def save_session(self, session: Session) -> None:
        session.updated_at = _now()
        await self._db.execute(
            """
            INSERT INTO sessions
                (id, task_id, task_description, task_repo_path, task_created_at,
                 status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                session.id,
                session.task.id,
                session.task.description,
                session.task.repo_path,
                session.task.created_at.isoformat(),
                session.status,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def load_session(self, session_id: str) -> Session | None:
        async with self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None

        task = Task(
            id=row[1],
            description=row[2],
            repo_path=row[3],
            created_at=datetime.fromisoformat(row[4]),
        )
        session = Session(
            id=row[0],
            task=task,
            status=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )
        session.subtasks = await self._load_subtasks(session_id)
        session.checkpoints = await self._load_checkpoints(session_id)
        return session

    async def list_sessions(self, limit: int = 20) -> list[Session]:
        async with self._db.execute(
            "SELECT id FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        sessions = []
        for (sid,) in rows:
            s = await self.load_session(sid)
            if s is not None:
                sessions.append(s)
        return sessions

    # --- Subtask ---

    async def save_subtask(self, subtask: Subtask) -> None:
        import json

        subtask.updated_at = _now()
        await self._db.execute(
            """
            INSERT INTO subtasks
                (id, session_id, agent, input, output, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                output = excluded.output,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                subtask.id,
                subtask.session_id,
                subtask.agent,
                json.dumps(subtask.input),
                json.dumps(subtask.output) if subtask.output is not None else None,
                subtask.status,
                subtask.created_at.isoformat(),
                subtask.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def _load_subtasks(self, session_id: str) -> list[Subtask]:
        import json

        async with self._db.execute(
            "SELECT * FROM subtasks WHERE session_id = ? ORDER BY created_at", (session_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [
            Subtask(
                id=r[0],
                session_id=r[1],
                agent=r[2],
                input=json.loads(r[3]),
                output=json.loads(r[4]) if r[4] is not None else None,
                status=r[5],
                created_at=datetime.fromisoformat(r[6]),
                updated_at=datetime.fromisoformat(r[7]),
            )
            for r in rows
        ]

    # --- Checkpoint ---

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        await self._db.execute(
            """
            INSERT INTO checkpoints
                (id, session_id, type, message, response, resolved_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                response = excluded.response,
                resolved_at = excluded.resolved_at
            """,
            (
                checkpoint.id,
                checkpoint.session_id,
                checkpoint.type,
                checkpoint.message,
                checkpoint.response,
                checkpoint.resolved_at.isoformat() if checkpoint.resolved_at else None,
                checkpoint.created_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def _load_checkpoints(self, session_id: str) -> list[Checkpoint]:
        async with self._db.execute(
            "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at", (session_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [
            Checkpoint(
                id=r[0],
                session_id=r[1],
                type=r[2],
                message=r[3],
                response=r[4],
                resolved_at=datetime.fromisoformat(r[5]) if r[5] else None,
                created_at=datetime.fromisoformat(r[6]),
            )
            for r in rows
        ]
