from __future__ import annotations

import asyncio
import logging

from abie_gpt.app.service import ChatService
from abie_gpt.core.config import Settings
from abie_gpt.core.logging import tail_log

logger = logging.getLogger(__name__)


class MaxBotHandler:
    """MAX transport adapter. It contains no Selenium logic."""

    def __init__(self, settings: Settings, service: ChatService, *, bot=None, dispatcher=None):
        self.settings = settings
        self.service = service
        if bot is None or dispatcher is None:
            from maxapi import Bot, Dispatcher
            bot = bot or Bot(settings.max_bot_token)
            dispatcher = dispatcher or Dispatcher()
        self.bot = bot
        self.dispatcher = dispatcher
        self.dispatcher.message_created()(self.on_message)

    async def on_message(self, event) -> None:
        text = (event.message.body.text or "").strip()
        if not text:
            return
        command = text.casefold()
        key = self._conversation_key(event)
        logger.info("MAX incoming key=%s chars=%d command=%s", key, len(text), command.startswith("/"))
        waiting = None
        try:
            if command in {"/new", "нд", "новый диалог"}:
                chat = await asyncio.to_thread(self.service.new_chat, key)
                await event.message.answer(f"Новый диалог открыт: {chat.url}")
                return
            if command in {"/stop", "стоп"}:
                stopped = await asyncio.to_thread(self.service.stop)
                await event.message.answer("Генерация остановлена." if stopped else "Активной генерации нет.")
                return
            if command in {"/status", "статус"}:
                await event.message.answer("ChatGPT: " + await asyncio.to_thread(self.service.status))
                return
            if command.startswith("/logs"):
                parts = command.split(maxsplit=1)
                count = 100
                if len(parts) == 2:
                    try:
                        count = max(1, min(int(parts[1]), 1000))
                    except ValueError:
                        await event.message.answer("Использование: /logs или /logs 200")
                        return
                log_text = tail_log(self.settings.log_dir / "abie-gpt.log", count)
                chunks = split_message(log_text, self.settings.max_message_length)
                for chunk in chunks or ["Лог пока пуст."]:
                    await event.message.answer(chunk)
                return
            if command in {"/screenshot", "сш"}:
                path = await asyncio.to_thread(self.service.screenshot)
                await event.message.answer(f"Скриншот: {path.name}")
                return

            waiting = await event.message.answer("⏳ Жду ответ ChatGPT…")
            logger.info("ChatGPT request key=%s prompt_chars=%d", key, len(text))
            answer = await asyncio.to_thread(self.service.ask, key, text)
            logger.info("ChatGPT response key=%s chars=%d", key, len(answer))
            chunks = split_message(answer, self.settings.max_message_length)
            logger.info("MAX delivery key=%s chunks=%d", key, len(chunks))
            if waiting is not None and chunks:
                await self._edit_sent_message(waiting, chunks[0])
                logger.info("MAX edit key=%s chunk=1 chars=%d", key, len(chunks[0]))
                for index, chunk in enumerate(chunks[1:], 2):
                    await event.message.answer(chunk)
                    logger.info("MAX send key=%s chunk=%d chars=%d", key, index, len(chunk))
            else:
                for index, chunk in enumerate(chunks, 1):
                    await event.message.answer(chunk)
                    logger.info("MAX send key=%s chunk=%d chars=%d", key, index, len(chunk))
        except Exception as exc:
            logger.exception("MAX handler failed key=%s", key)
            error = f"❌ Ошибка: {type(exc).__name__}: {exc}"
            if waiting is not None:
                try:
                    await self._edit_sent_message(waiting, error)
                    return
                except Exception:
                    logger.exception("Could not edit MAX waiting message key=%s", key)
            await event.message.answer(error)

    def _conversation_key(self, event) -> str:
        message = event.message
        recipient = getattr(message, "recipient", None)
        chat_id = getattr(recipient, "chat_id", None) or getattr(message, "chat_id", None)
        sender = getattr(message, "sender", None)
        user_id = getattr(sender, "user_id", None) or getattr(message, "sender_id", None)
        value = chat_id or user_id
        if value is None:
            raise RuntimeError("MAX event has no stable conversation identifier")
        return str(value)

    async def _edit_sent_message(self, message, text: str) -> None:
        edit = getattr(message, "edit", None)
        if callable(edit):
            await edit(text=text)
            return
        sent_message = getattr(message, "message", None)
        body = getattr(sent_message, "body", None) or getattr(message, "body", None)
        message_id = getattr(body, "mid", None) or getattr(message, "message_id", None)
        if not message_id:
            raise RuntimeError("MAX did not return the sent message id")
        await self.bot.edit_message(message_id=str(message_id), text=text)

    async def run(self) -> None:
        logger.info("MAX polling started")
        await self.dispatcher.start_polling(self.bot)


def split_message(text: str, limit: int) -> list[str]:
    if limit < 1:
        raise ValueError("Message limit must be positive")
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
