"""Shared pytest fixtures for all test suites."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from map.session.state import SessionStore


@pytest.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """In-memory SQLite connection with schema applied."""
    async with aiosqlite.connect(":memory:") as conn:
        await SessionStore.apply_schema(conn)
        yield conn


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Mock anthropic.AsyncAnthropic client with a pre-configured messages.create response."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="mock response", type="text")],
            stop_reason="end_turn",
        )
    )
    return client


@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Mock asyncio subprocess that returns exit code 0 and sample stdout."""

    async def fake_communicate() -> tuple[bytes, bytes]:
        return b"mock claude output\n", b""

    proc = MagicMock()
    proc.communicate = fake_communicate
    proc.returncode = 0
    return proc


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
