from __future__ import annotations

import asyncio

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

from .config import Settings
from .selenium_handler import ChatGPTHandler


class MaxChatApp:
    def __init__(self, settings: Settings, gpt: ChatGPTHandler):
        self.settings = settings
        self.gpt = gpt
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
                chat = await asyncio.to_thread(self.gpt.new_chat)
                await event.message.answer(f"Новый диалог открыт: {chat.url}")
                return
            if command in {"/stop", "стоп"}:
                stopped = await asyncio.to_thread(self.gpt.stop_generation)
                await event.message.answer("Генерация остановлена." if stopped else "Активной генерации нет.")
                return
            if command in {"/status", "статус"}:
                state = await asyncio.to_thread(self.gpt.health)
                await event.message.answer(f"ChatGPT: {state.value}")
                return
            if command in {"/screenshot", "сш"}:
                path = await asyncio.to_thread(self.gpt.screenshot)
                await event.message.answer(f"Скриншот: {path.name}")
                return

            response = await asyncio.to_thread(self.gpt.send_and_wait, text)
            for chunk in self._split(response.text):
                await event.message.answer(chunk)
        except Exception as exc:
            await event.message.answer(f"Ошибка: {type(exc).__name__}: {exc}")

    def _split(self, text: str) -> list[str]:
        limit = self.settings.max_message_length
        chunks = []
        remaining = text.strip()
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

    async def run(self) -> None:
        await asyncio.to_thread(self.gpt.start)
        try:
            await self.dispatcher.start_polling(self.bot)
        finally:
            await asyncio.to_thread(self.gpt.close)
