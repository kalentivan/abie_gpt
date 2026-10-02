from __future__ import annotations

import asyncio

from abie_gpt.app.service import ChatService
from abie_gpt.bot.max_handler import MaxBotHandler
from abie_gpt.chatgpt import ChatGPTHandler
from abie_gpt.core.config import Settings


async def run_max_app() -> None:
    settings = Settings.from_env()
    chatgpt = ChatGPTHandler(settings)
    chatgpt.start()
    try:
        await MaxBotHandler(settings, ChatService(chatgpt)).run()
    finally:
        chatgpt.close()


def main() -> None:
    asyncio.run(run_max_app())
