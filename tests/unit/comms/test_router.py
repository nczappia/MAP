"""Unit tests for CommsRouter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from map.comms.base import CommsRouter


def make_comm(reply: str | None = "yes", delay: float = 0) -> MagicMock:
    async def _reply(timeout_secs: float | None = None) -> str | None:
        if delay:
            await asyncio.sleep(delay)
        return reply

    comm = MagicMock()
    comm.send = AsyncMock()
    comm.wait_for_reply = _reply
    return comm


class TestCommsRouter:
    def test_requires_at_least_one_channel(self) -> None:
        with pytest.raises(ValueError):
            CommsRouter([])

    async def test_send_broadcasts_to_all_channels(self) -> None:
        c1 = make_comm()
        c2 = make_comm()
        router = CommsRouter([c1, c2])
        await router.send("hello")
        c1.send.assert_awaited_once_with("hello")
        c2.send.assert_awaited_once_with("hello")

    async def test_wait_for_reply_returns_first_response(self) -> None:
        fast = make_comm(reply="fast answer", delay=0)
        slow = make_comm(reply="slow answer", delay=10)
        router = CommsRouter([fast, slow])
        result = await router.wait_for_reply(timeout_secs=2)
        assert result == "fast answer"

    async def test_wait_for_reply_returns_none_on_timeout(self) -> None:
        slow = make_comm(reply="too late", delay=10)
        router = CommsRouter([slow])
        result = await router.wait_for_reply(timeout_secs=0.05)
        assert result is None

    async def test_wait_for_reply_cancels_pending_tasks(self) -> None:
        cancelled: list[bool] = []

        async def slow_reply(timeout_secs: float | None = None) -> str | None:
            try:
                await asyncio.sleep(10)
                return "answer"
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        fast = make_comm(reply="quick", delay=0)
        slow = MagicMock()
        slow.send = AsyncMock()
        slow.wait_for_reply = slow_reply

        router = CommsRouter([fast, slow])
        result = await router.wait_for_reply(timeout_secs=2)
        assert result == "quick"
        # give event loop a tick to process cancellations
        await asyncio.sleep(0)
        assert cancelled

    async def test_single_channel_works(self) -> None:
        comm = make_comm(reply="approved")
        router = CommsRouter([comm])
        result = await router.wait_for_reply()
        assert result == "approved"
