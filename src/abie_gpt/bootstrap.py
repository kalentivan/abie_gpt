from __future__ import annotations

import asyncio

from abie_gpt.app.service import ChatService
from abie_gpt.bot.max_handler import MaxBotHandler
from abie_gpt.chatgpt import ChatGPTHandler
from abie_gpt.core.config import Settings
from abie_gpt.storage import Database


async def run_max_app() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_url)
    database.create_schema()
    chatgpt = ChatGPTHandler(settings)
    await asyncio.to_thread(chatgpt.start)
    try:
        await MaxBotHandler(settings, ChatService(chatgpt, database)).run()
    finally:
        await asyncio.to_thread(chatgpt.close)


def main() -> None:
    asyncio.run(run_max_app())
