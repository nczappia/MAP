"""Unit tests for TerminalCommunicator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from map.comms.terminal import TerminalCommunicator


class TestTerminalCommunicator:
    async def test_send_prints_message(self, capsys: object) -> None:
        comm = TerminalCommunicator()
        await comm.send("approve the plan?")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "approve the plan?" in captured.out

    async def test_send_prints_separator(self, capsys: object) -> None:
        comm = TerminalCommunicator()
        await comm.send("hello")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "=" * 10 in captured.out

    async def test_wait_for_reply_returns_stripped_input(self) -> None:
        comm = TerminalCommunicator()
        with patch("asyncio.wait_for", AsyncMock(return_value="  yes  ")):
            result = await comm.wait_for_reply()
        assert result == "yes"

    async def test_wait_for_reply_timeout_returns_none(self) -> None:
        import asyncio

        comm = TerminalCommunicator()
        with patch("asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await comm.wait_for_reply(timeout_secs=0.001)
        assert result is None
