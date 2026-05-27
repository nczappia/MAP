"""Terminal communicator: sends to stdout, reads from stdin."""

from __future__ import annotations

import asyncio

from map.comms.base import Communicator


class TerminalCommunicator(Communicator):
    """Human-in-the-loop via the local terminal (always available as fallback)."""

    async def send(self, message: str) -> None:
        print(f"\n{'=' * 60}")
        print(message)
        print("=" * 60)

    async def wait_for_reply(self, timeout_secs: float | None = None) -> str | None:
        loop = asyncio.get_event_loop()
        try:
            reply = await asyncio.wait_for(
                loop.run_in_executor(None, input, "\nYour reply: "),
                timeout=timeout_secs,
            )
            return reply.strip()
        except asyncio.TimeoutError:
            return None
