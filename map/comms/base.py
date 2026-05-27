"""Abstract Communicator interface and CommsRouter."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class Communicator(ABC):
    """Single communication channel (terminal, Telegram, SMS, etc.)."""

    @abstractmethod
    async def send(self, message: str) -> None:
        """Send a message outbound on this channel."""
        ...

    @abstractmethod
    async def wait_for_reply(self, timeout_secs: float | None = None) -> str | None:
        """Block until a reply arrives on this channel.

        Returns the reply text, or None if timeout_secs elapsed without a reply.
        """
        ...


class CommsRouter:
    """Broadcasts to multiple channels and accepts the first reply from any."""

    def __init__(self, channels: list[Communicator]) -> None:
        if not channels:
            raise ValueError("CommsRouter requires at least one channel")
        self._channels = channels

    async def send(self, message: str) -> None:
        """Send message to all channels concurrently."""
        await asyncio.gather(*(ch.send(message) for ch in self._channels))

    async def wait_for_reply(self, timeout_secs: float | None = None) -> str | None:
        """Wait for the first reply from any channel.

        Returns the reply text from whichever channel responds first, or None on timeout.
        """
        tasks = {asyncio.create_task(ch.wait_for_reply(timeout_secs)): ch for ch in self._channels}
        try:
            done, pending = await asyncio.wait(
                tasks.keys(),
                timeout=timeout_secs,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if not done:
                return None
            return done.pop().result()
        except Exception:
            for t in tasks:
                t.cancel()
            raise
