import asyncio
import traceback
from pathlib import Path

import maxapi
from maxapi import Bot, Dispatcher
from maxapi.types import InputMedia, MessageCreated

from config import settings
from features.abie import AbieHttpExecutor, REQUEST_PROMPT, parse_command
from integrations.chatgpt import ChatGPTHandler
from utils.media import download_attachments, extract_archives, is_audio_file, transcribe_audio
from utils.repo_snapshot import create_repo_snapshot, parse_pull_command
from features.taxi import TaxiAgent

bot = Bot(settings.max_bot_token)
dp = Dispatcher()
gpt = ChatGPTHandler()
taxi = TaxiAgent()
abie_http = AbieHttpExecutor()
last_files: list[Path] = []
bot_mode = "GPT"  # GPT | TAXI
abie_stop_requested = False


async def send_files(message, paths: list[Path]) -> None:
    for path in paths:
        await message.answer(text=path.name, attachments=[InputMedia(path=str(path))])


async def send_text(message, value: str) -> None:
    for i in range(0, len(value), 3900):
        await message.answer(value[i:i + 3900])


async def execute_abie_request(message, command):
    await message.answer(f"🔧 {command.target}\n{command.raw_command}")
    result = await asyncio.to_thread(abie_http.execute, command)
    await message.answer(
        text=(
            f"HTTP {result.status_code} · {result.size} bytes · "
            f"{result.duration_seconds:.2f}s\n"
            f"Результат: {result.file_path.name}"
        ),
        attachments=[InputMedia(path=str(result.file_path))],
    )
    return result


async def run_abie_dialog(message) -> None:
    global abie_stop_requested
    abie_stop_requested = False

    answer, outgoing = await asyncio.to_thread(gpt.send_with_files, REQUEST_PROMPT, [])
    if outgoing:
        await send_files(message, outgoing)

    steps = 0
    while True:
        if abie_stop_requested:
            await message.answer("ABIE: цепочка остановлена. Возвращаюсь в ручной режим.")
            return

        command = parse_command(answer)
        if command is None:
            await send_text(message, answer)
            return

        steps += 1
        if steps > settings.abie_max_request_chain:
            await message.answer(
                f"ABIE: достигнут предохранительный лимит "
                f"{settings.abie_max_request_chain} запросов. Цепочка остановлена."
            )
            return

        result = await execute_abie_request(message, command)

        result_prompt = (
            "Результат выполненного HTTP-запроса приложен файлом. "
            f"Команда: {command.raw_command}. HTTP status: {result.status_code}. "
            f"Размер payload: {result.size} bytes. "
            "Проанализируй результат. Если нужен следующий запрос и ранее была "
            "согласована автоматическая цепочка, ответь только следующей машинной "
            "командой и добавь последней строкой «ПРОДОЛЖАЕМ РАБОТУ». "
            "Если запросов больше не нужно, дай обычный ответ пользователю."
        )
        answer, outgoing = await asyncio.to_thread(
            gpt.send_with_files,
            result_prompt,
            [result.file_path],
        )
        if outgoing:
            await send_files(message, outgoing)

        # A request is followed automatically only when the command that was
        # just executed explicitly carried the continuation marker.
        if not command.continue_work:
            await send_text(message, answer)
            return


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
    global last_files, bot_mode, abie_stop_requested
    text = (event.message.body.text or "").strip()
    attachments = list(event.message.body.attachments or [])

    try:
        incoming = await asyncio.to_thread(download_attachments, attachments)
        if incoming:
            last_files = incoming
            await event.message.answer("Файл получен: " + ", ".join(p.name for p in incoming))

        folded = text.casefold()

        if folded in {"стоп", "stop"}:
            abie_stop_requested = True
            await event.message.answer("СТОП принят. Автоматическая цепочка ABIE остановлена.")
            try:
                await asyncio.to_thread(
                    gpt.send,
                    "Пользователь отправил СТОП. Не отправляй следующие HTTP-запросы; "
                    "переходим в ручной режим.",
                )
            except Exception:
                traceback.print_exc()
            return

        if folded in {"выполни запрос", "выполнить запрос"}:
            await event.message.answer("ABIE: запрашиваю у ChatGPT машинную HTTP-команду.")
            await run_abie_dialog(event.message)
            return

        if folded in {"abie api", "аби api", "abie openapi", "аби openapi"}:
            command = abie_http.openapi_command()
            result = await execute_abie_request(event.message, command)
            answer, outgoing = await asyncio.to_thread(
                gpt.send_with_files,
                (
                    "Актуальный OpenAPI bundle работающей ABIE приложен. "
                    "Используй его как источник истины для доступных HTTP API, "
                    "методов и аргументов при следующих диагностических запросах."
                ),
                [result.file_path],
            )
            await send_text(event.message, answer)
            if outgoing:
                await send_files(event.message, outgoing)
            return

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

        if text.upper() == "НД" or text.upper().startswith("НД "):
            title = text[2:].strip() or None
            item = await asyncio.to_thread(gpt.new_dialog, title)
            await event.message.answer(
                f"Новый диалог создан и сохранён: {item['title']}\n{item['url']}"
            )
            return

        if folded in {"диалоги", "список диалогов"}:
            items = await asyncio.to_thread(gpt.list_dialogs)
            if not items:
                await event.message.answer("Сохранённых диалогов пока нет.")
                return
            lines = ["Диалоги ChatGPT:"]
            for index, item in enumerate(items, 1):
                marker = " ← текущий" if item.get("active") else ""
                lines.append(
                    f"{index}. {item['title']}{marker}\n{item['url']}"
                )
            await send_text(event.message, "\n".join(lines))
            return

        if folded.startswith("диалог "):
            selector = text.split(maxsplit=1)[1].strip()
            item = await asyncio.to_thread(gpt.switch_dialog, selector)
            await event.message.answer(
                f"Переключился на диалог: {item['title']}\n{item['url']}"
            )
            return

        if text.upper() == "СШ":
            path = await asyncio.to_thread(gpt.screenshot)
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
            answer, outgoing = await asyncio.to_thread(gpt.send_with_files, prompt, [archive])
            await event.message.answer("ПУЛЛ: ChatGPT ответил. Отправляю ответ в MAX.")
            await send_text(event.message, answer)
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
        answer, outgoing = await asyncio.to_thread(
            gpt.send_with_files,
            text or "Посмотри приложенные файлы.",
            files_for_gpt,
        )

        await send_text(event.message, answer)
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
    print("НД [название] = новый диалог | ДИАЛОГИ = список | ДИАЛОГ <номер/название> = переключить | СШ = скриншот | ПУЛЛ <ветка> = snapshot ABIE -> ChatGPT | РАСПАКУЙ = извлечь архив | Закажи такси | Выполни запрос | ABIE API | СТОП")
    try:
        await dp.start_polling(bot)
    finally:
        await asyncio.to_thread(taxi.close)
        await asyncio.to_thread(gpt.close)


if __name__ == "__main__":
    asyncio.run(main())
