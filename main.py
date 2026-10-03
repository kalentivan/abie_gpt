import asyncio
import os
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import maxapi
from maxapi import Bot, Dispatcher
from maxapi.types import InputMedia, MessageCreated

from handler import ChatGPTHandler
from media import download_attachments, extract_archives, is_audio_file, transcribe_audio

TOKEN = os.getenv("MAX_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("В .env не задан MAX_BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()
gpt = ChatGPTHandler()
last_files: list[Path] = []


async def send_files(message, paths: list[Path]) -> None:
    for path in paths:
        await message.answer(text=path.name, attachments=[InputMedia(path=str(path))])


@dp.message_created()
async def message(event: MessageCreated):
    global last_files
    text = (event.message.body.text or "").strip()
    attachments = list(event.message.body.attachments or [])

    try:
        incoming = await asyncio.to_thread(download_attachments, attachments)
        if incoming:
            last_files = incoming
            await event.message.answer("Файл получен: " + ", ".join(p.name for p in incoming))

        if text.upper() == "НД":
            await asyncio.to_thread(gpt.new_dialog)
            await event.message.answer("Новый диалог открыт.")
            return

        if text.upper() == "СШ":
            path = await asyncio.to_thread(gpt.screenshot)
            await send_files(event.message, [path])
            return

        if text.upper() == "РАСПАКУЙ":
            archives = incoming or last_files
            if not archives:
                await event.message.answer("Сначала пришли архив.")
                return
            extracted = await asyncio.to_thread(extract_archives, archives)
            last_files = extracted
            await send_files(event.message, extracted)
            return

        audio = [p for p in incoming if is_audio_file(p)]
        if audio:
            spoken = "\n".join(
                await asyncio.to_thread(transcribe_audio, p) for p in audio
            ).strip()
            if spoken:
                text = f"{text}\n{spoken}".strip()
                await event.message.answer(f"🎙 {spoken}")

        files_for_gpt = [p for p in incoming if p not in audio]
        if not text and not files_for_gpt:
            return

        print(f"MAX <- {text!r}; files={[p.name for p in files_for_gpt]!r}")
        answer, outgoing = await asyncio.to_thread(
            gpt.send_with_files,
            text or "Посмотри приложенные файлы.",
            files_for_gpt,
        )

        for i in range(0, len(answer), 3900):
            await event.message.answer(answer[i:i + 3900])
        if outgoing:
            await send_files(event.message, outgoing)

    except Exception as error:
        traceback.print_exc()
        await event.message.answer(f"Ошибка: {type(error).__name__}: {error}")


async def main():
    print(f"maxapi loaded from: {Path(maxapi.__file__).resolve()}")
    try:
        from maxapi.enums.update import UpdateType
        print("maxapi update types:", [str(item.value) for item in UpdateType])
    except Exception as error:
        print(f"maxapi diagnostics failed: {error}")
    await asyncio.to_thread(gpt.start)
    print("MAX <-> ChatGPT запущен")
    print("НД = новый диалог | СШ = скриншот | РАСПАКУЙ = извлечь архив")
    try:
        await dp.start_polling(bot)
    finally:
        await asyncio.to_thread(gpt.close)


if __name__ == "__main__":
    asyncio.run(main())
