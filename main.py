import asyncio
import os
import traceback

from dotenv import load_dotenv

load_dotenv()

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

from handler import ChatGPTHandler


TOKEN = os.getenv("MAX_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("В .env не задан MAX_BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()
gpt = ChatGPTHandler()


@dp.message_created()
async def message(event: MessageCreated):
    text = (event.message.body.text or "").strip()
    if not text:
        return

    print(f"MAX <- {text!r}")

    try:
        if text.upper() == "НД":
            await asyncio.to_thread(gpt.new_dialog)
            await event.message.answer("Новый диалог открыт.")
            return

        if text.upper() == "СШ":
            path = await asyncio.to_thread(gpt.screenshot)
            await event.message.answer(f"Скриншот сделан: {path.name}")
            return

        answer = await asyncio.to_thread(gpt.send, text)

        # На случай длинных ответов.
        for i in range(0, len(answer), 3900):
            await event.message.answer(answer[i:i + 3900])

    except Exception as error:
        traceback.print_exc()
        await event.message.answer(
            f"Ошибка: {type(error).__name__}: {error}"
        )


async def main():
    await asyncio.to_thread(gpt.start)
    print("MAX <-> ChatGPT запущен")
    print("НД = новый диалог | СШ = скриншот")

    try:
        await dp.start_polling(bot)
    finally:
        await asyncio.to_thread(gpt.close)


if __name__ == "__main__":
    asyncio.run(main())