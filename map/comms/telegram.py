"""Telegram communicator: sends checkpoint messages and waits for replies via Telegram Bot API."""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters

from map.comms.base import Communicator

logger = logging.getLogger(__name__)


class TelegramCommunicator(Communicator):
    """Sends messages to a Telegram chat and waits for the user's reply.

    Setup:
        1. Create a bot via @BotFather and copy the token into TELEGRAM_BOT_TOKEN.
        2. Send /start to your bot, then look up your chat ID (e.g. via @userinfobot).
        3. Set TELEGRAM_ALLOWED_CHAT_ID to your numeric chat ID.

    Only messages from allowed_chat_id are accepted as checkpoint replies.
    """

    def __init__(self, token: str, allowed_chat_id: str | int) -> None:
        self._token = token
        self._allowed_chat_id = int(allowed_chat_id)
        self._bot = Bot(token=token)

    async def send(self, message: str) -> None:
        """Send message to the allowed Telegram chat."""
        await self._bot.send_message(
            chat_id=self._allowed_chat_id,
            text=message,
        )

    async def wait_for_reply(self, timeout_secs: float | None = None) -> str | None:
        """Start a temporary update handler and wait for the first message from the allowed chat.

        Returns the message text, or None on timeout.
        """
        reply_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        async def handler(update: Update, context: object) -> None:
            if update.message is None:
                return
            if update.effective_chat is None:
                return
            if update.effective_chat.id != self._allowed_chat_id:
                logger.warning(
                    "Ignoring message from unauthorized chat %s", update.effective_chat.id
                )
                return
            if not reply_future.done():
                reply_future.set_result(update.message.text or "")

        app = Application.builder().token(self._token).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

        async with app:
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)  # type: ignore[union-attr]
            try:
                return await asyncio.wait_for(reply_future, timeout=timeout_secs)
            except asyncio.TimeoutError:
                return None
            finally:
                await app.updater.stop()  # type: ignore[union-attr]
                await app.stop()
