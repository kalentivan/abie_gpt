from __future__ import annotations

import asyncio

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

from abie_gpt.app.service import ChatService
from abie_gpt.core.config import Settings


class MaxBotHandler:
    """MAX transport adapter. It contains no Selenium logic."""

    def __init__(self, settings: Settings, service: ChatService):
        self.settings = settings
        self.service = service
        self.bot = Bot(settings.max_bot_token)
        self.dispatcher = Dispatcher()
        self.dispatcher.message_created()(self.on_message)

    async def on_message(self, event: MessageCreated) -> None:
        text = (event.message.body.text or "").strip()
        if not text:
            return
        command = text.casefold()
        try:
            if command in {"/new", "нд", "новый диалог"}:
                key = self._conversation_key(event)\n                chat = await asyncio.to_thread(self.service.new_chat, key)
                await event.message.answer(f"Новый диалог открыт: {chat.url}")
                return
            if command in {"/stop", "стоп"}:
                stopped = await asyncio.to_thread(self.service.stop)
                await event.message.answer("Генерация остановлена." if stopped else "Активной генерации нет.")
                return
            if command in {"/status", "статус"}:
                await event.message.answer("ChatGPT: " + await asyncio.to_thread(self.service.status))
                return
            if command in {"/screenshot", "сш"}:
                path = await asyncio.to_thread(self.service.screenshot)
                await event.message.answer(f"Скриншот: {path.name}")
                return

            key = self._conversation_key(event)\n            answer = await asyncio.to_thread(self.service.ask, key, text)
            for chunk in split_message(answer, self.settings.max_message_length):
                await event.message.answer(chunk)
        except Exception as exc:
            await event.message.answer(f"Ошибка: {type(exc).__name__}: {exc}")

    async def run(self) -> None:
        await self.dispatcher.start_polling(self.bot)


def split_message(text: str, limit: int) -> list[str]:
    chunks, remaining = [], text.strip()
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
