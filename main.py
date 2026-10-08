import asyncio
import traceback
import logging
from pathlib import Path

import maxapi
from maxapi import Bot, Dispatcher
from maxapi.types import InputMedia, MessageCreated

from config import settings
from integrations.chatgpt import ChatGPTHandler
from utils.media import download_attachments, extract_archives, is_audio_file, transcribe_audio
from utils.repo_snapshot import create_repo_snapshot, parse_pull_command
from features.taxi import TaxiAgent

bot = Bot(settings.max_bot_token)
dp = Dispatcher()
gpt = ChatGPTHandler()
taxi = TaxiAgent()
last_files: list[Path] = []
bot_mode = "GPT"  # GPT | TAXI
browser_lock = asyncio.Lock()
active_tasks = set()

async def browser_call(fn, *args):
    async with browser_lock:
        for attempt in range(2):
            try:
                if gpt.driver is None:
                    await asyncio.to_thread(gpt.start)
                return await asyncio.to_thread(fn, *args)
            except Exception:
                if attempt or fn.__name__ in {"send_with_files", "send"}:
                    raise
                logging.exception("Browser operation failed; reconnecting")
                gpt.driver = None
                await asyncio.sleep(2)

async def acknowledge(message):
    try:
        return await message.answer("Жду ответа...")
    except Exception:
        logging.exception("Acknowledgement failed")
        return None

async def finish_message(message, placeholder, answer):
    if placeholder is not None:
        try:
            edit = getattr(getattr(placeholder, "message", None), "edit", None)
            if callable(edit):
                await edit(text=answer)
                return
        except Exception:
            logging.exception("Cannot edit placeholder; sending separately")
    await message.answer(answer)

def spawn(coro):
    task = asyncio.create_task(coro)
    active_tasks.add(task)
    def done(finished):
        active_tasks.discard(finished)
        if not finished.cancelled():
            try:
                finished.result()
            except Exception:
                logging.exception("Background command failed")
    task.add_done_callback(done)



async def send_files(message, paths: list[Path]) -> None:
    for path in paths:
        await message.answer(text=path.name, attachments=[InputMedia(path=str(path))])


async def monitor_taxi(message) -> None:
    last_state = None
    screenshot_sent = False
    while taxi.state in {"ORDERING", "SEARCHING_CAR", "CAR_ASSIGNED"}:
        await asyncio.sleep(10)
        try:
            await asyncio.to_thread(taxi.status)
            if taxi.state != last_state:
                if taxi.state == "SEARCHING_CAR":
                    await message.answer("Яндекс ещё ищет машину.")
                elif taxi.state == "CAR_ASSIGNED" and not screenshot_sent:
                    path = await asyncio.to_thread(taxi.provider.diagnostic, "car-assigned")
                    await message.answer(
                        text="Машина найдена — вот экран заказа.",
                        attachments=[InputMedia(path=str(path))],
                    )
                    screenshot_sent = True
                    return
                last_state = taxi.state
            if taxi.state == "ARRIVED":
                return
        except Exception as error:
            print(f"[TAXI] monitor error: {type(error).__name__}: {error}", flush=True)
            return


@dp.message_created()
async def message(event: MessageCreated):
    text = (event.message.body.text or "").strip()
    if text.casefold() in {"пинг", "ping"}:
        try:
            await event.message.answer("ОК")
        except Exception:
            logging.exception("PING failed")
        return
    spawn(process_message(event))

async def process_message(event: MessageCreated):
    global last_files, bot_mode
    text = (event.message.body.text or "").strip()
    attachments = list(event.message.body.attachments or [])

    placeholder = await acknowledge(event.message)
    try:
        incoming = await asyncio.to_thread(download_attachments, attachments)
        if incoming:
            last_files = incoming
            await event.message.answer("Файл получен: " + ", ".join(p.name for p in incoming))

        folded = text.casefold()

        if folded in {"режим gpt", "режим гпт", "gpt", "гпт"}:
            bot_mode = "GPT"
            await event.message.answer("Режим GPT включён.")
            return

        if folded in {"режим такси", "такси режим"}:
            bot_mode = "TAXI"
            await event.message.answer(
                "Режим такси включён. Напиши «Закажи такси» или «Закажи такси 1 2»."
            )
            return

        if folded in {"статус", "статус такси", "где машина", "когда машина"} and bot_mode == "TAXI":
            path = await asyncio.to_thread(taxi.provider.diagnostic, "status")
            await event.message.answer(
                text=f"Статус такси: {taxi.state}. Текущий экран Яндекс Go:",
                attachments=[InputMedia(path=str(path))],
            )
            return

        if text.casefold() in {"такси dom", "такси дом", "taxi dom"}:
            paths = await asyncio.to_thread(taxi.provider.dump_dom)
            await event.message.answer("Диагностика Яндекс Go готова.")
            await send_files(event.message, paths)
            return

        taxi_command = text.split(maxsplit=2)
        if (
            taxi_command
            and (
                text.casefold() in {"закажи такси", "такси", "вызови такси"}
                or text.casefold().startswith("закажи такси ")
                or text.casefold().startswith("вызови такси ")
            )
        ):
            bot_mode = "TAXI"
            route = ""
            folded = text.casefold()
            for prefix in ("закажи такси", "вызови такси", "такси"):
                if folded == prefix or folded.startswith(prefix + " "):
                    route = text[len(prefix):].strip()
                    break

            answer = await asyncio.to_thread(taxi.start)
            if route:
                # Same state machine as the two-message flow, just feed the
                # remembered address numbers immediately.
                answer = await asyncio.to_thread(taxi.handle, route)
            await event.message.answer(answer)
            return

        if bot_mode == "TAXI" and taxi.is_active() and not incoming:
            answer = await asyncio.to_thread(taxi.handle, text)
            await event.message.answer(answer)
            if taxi.state == "ORDERING":
                asyncio.create_task(monitor_taxi(event.message))
            return

        if bot_mode == "TAXI" and not incoming:
            await event.message.answer(
                "Сейчас включён режим такси. Команды: «Закажи такси», «Статус», "
                "«Режим GPT»."
            )
            return

        if folded == "сд":
            names = await asyncio.to_thread(gpt.list_dialogs)
            await finish_message(event.message, placeholder, "Диалоги:\n" + "\n".join(names) if names else "Список диалогов пуст.")
            return

        if folded == "нд" or folded.startswith("нд "):
            name = text[2:].strip() or None
            await browser_call(gpt.new_dialog, name)
            await finish_message(event.message, placeholder, f"Новый диалог открыт: {name}" if name else "Новый диалог открыт.")
            return

        if folded.startswith("д ") or folded.startswith("диалог "):
            name = text.split(maxsplit=1)[1].strip()
            await browser_call(gpt.switch_dialog, name)
            await finish_message(event.message, placeholder, f"Переключено на диалог: {name}")
            return

        if text.upper() == "СШ":
            path = await browser_call(gpt.screenshot)
            await send_files(event.message, [path])
            return

        pull_version = parse_pull_command(text)
        if pull_version:
            await event.message.answer(f"ПУЛЛ {pull_version}: начинаю.")
            loop = asyncio.get_running_loop()

            def progress(status):
                print(f"[PULL] {status}", flush=True)
                asyncio.run_coroutine_threadsafe(
                    event.message.answer(f"ПУЛЛ: {status}"),
                    loop,
                )

            archive, branch, commit = await asyncio.to_thread(
                create_repo_snapshot,
                pull_version,
                progress,
            )
            await event.message.answer("ПУЛЛ: загружаю архив в ChatGPT...")
            prompt = f"ПУЛЛ {pull_version}: свежий snapshot ABIE ветки {branch}, commit {commit}. Архив приложен."
            answer, outgoing = await browser_call(gpt.send_with_files, prompt, [archive])
            await event.message.answer("ПУЛЛ: ChatGPT ответил. Отправляю ответ в MAX.")
            for i in range(0, len(answer), 3900):
                await event.message.answer(answer[i:i + 3900])
            if outgoing:
                await send_files(event.message, outgoing)
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
        answer, outgoing = await browser_call(
            gpt.send_with_files,
            text or "Посмотри приложенные файлы.",
            files_for_gpt,
        )

        await finish_message(event.message, placeholder, answer[:3900])
        for i in range(3900, len(answer), 3900):
            await event.message.answer(answer[i:i + 3900])
        if outgoing:
            await send_files(event.message, outgoing)

    except Exception as error:
        traceback.print_exc()
        try:
            await finish_message(event.message, placeholder, f"Ошибка: {type(error).__name__}: {error}")
        except Exception:
            logging.exception("Failed to report error")


async def main():
    print(f"maxapi loaded from: {Path(maxapi.__file__).resolve()}", flush=True)
    while True:
        try:
            await dp.start_polling(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("MAX polling crashed; restarting in 5 seconds")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
