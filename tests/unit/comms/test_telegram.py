"""Unit tests for TelegramCommunicator (all Telegram API calls are mocked)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from map.comms.telegram import TelegramCommunicator


def make_comm(allowed_chat_id: int = 12345) -> TelegramCommunicator:
    with patch("map.comms.telegram.Bot"):
        comm = TelegramCommunicator(token="fake-token", allowed_chat_id=allowed_chat_id)
    return comm


class TestTelegramCommunicator:
    async def test_send_calls_bot_send_message(self) -> None:
        comm = make_comm()
        comm._bot.send_message = AsyncMock()

        await comm.send("checkpoint message")

        comm._bot.send_message.assert_awaited_once_with(
            chat_id=12345,
            text="checkpoint message",
        )

    async def test_send_uses_allowed_chat_id(self) -> None:
        comm = make_comm(allowed_chat_id=99999)
        comm._bot.send_message = AsyncMock()

        await comm.send("hello")

        call_kwargs = comm._bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 99999

    async def test_wait_for_reply_returns_message_text(self) -> None:
        comm = make_comm()

        with patch("map.comms.telegram.Application") as mock_app_cls:
            # Build a minimal fake Application context manager
            mock_app = _make_fake_app(reply_text="approve", chat_id=12345)
            mock_app_cls.builder.return_value.token.return_value.build.return_value = mock_app

            with patch("asyncio.wait_for", AsyncMock(return_value="approve")):
                result = await comm.wait_for_reply(timeout_secs=5)

        assert result == "approve"

    async def test_wait_for_reply_timeout_returns_none(self) -> None:
        comm = make_comm()

        with patch("map.comms.telegram.Application") as mock_app_cls:
            mock_app = _make_fake_app(reply_text="too late", chat_id=12345)
            mock_app_cls.builder.return_value.token.return_value.build.return_value = mock_app

            with patch("asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)):
                result = await comm.wait_for_reply(timeout_secs=0.01)

        assert result is None

    async def test_allowed_chat_id_converted_to_int(self) -> None:
        with patch("map.comms.telegram.Bot"):
            comm = TelegramCommunicator(token="tok", allowed_chat_id="777")
        assert comm._allowed_chat_id == 777
        assert isinstance(comm._allowed_chat_id, int)


def _make_fake_app(reply_text: str, chat_id: int) -> MagicMock:
    """Build a mock telegram Application usable as an async context manager."""
    updater = MagicMock()
    updater.start_polling = AsyncMock()
    updater.stop = AsyncMock()

    app = MagicMock()
    app.updater = updater
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.add_handler = MagicMock()

    # Make app usable as `async with app:`
    app.__aenter__ = AsyncMock(return_value=app)
    app.__aexit__ = AsyncMock(return_value=False)

    return app
