from types import SimpleNamespace

import pytest

from abie_gpt.bot.max_handler import MaxBotHandler
from abie_gpt.core.config import Settings


class FakeDispatcher:
    def __init__(self):
        self.handler = None

    def message_created(self):
        def register(handler):
            self.handler = handler
            return handler
        return register

    async def start_polling(self, bot):
        return None


class FakeBot:
    def __init__(self):
        self.edits = []

    async def edit_message(self, message_id, text=None, **kwargs):
        self.edits.append((message_id, text))


class FakeSent:
    def __init__(self, mid):
        self.message = SimpleNamespace(body=SimpleNamespace(mid=mid))


class FakeMessage:
    def __init__(self, text, chat_id=42, user_id=7):
        self.body = SimpleNamespace(text=text)
        self.recipient = SimpleNamespace(chat_id=chat_id)
        self.sender = SimpleNamespace(user_id=user_id)
        self.answers = []
        self._counter = 0

    async def answer(self, text):
        self.answers.append(text)
        self._counter += 1
        return FakeSent(f"sent-{self._counter}")


class FakeEvent:
    def __init__(self, text):
        self.message = FakeMessage(text)


class FakeService:
    def __init__(self, answer="Готовый ответ", error=None):
        self.answer = answer
        self.error = error
        self.calls = []

    def ask(self, key, text):
        self.calls.append((key, text))
        if self.error:
            raise self.error
        return self.answer

    def status(self):
        return "ready"

    def stop(self):
        return True

    def screenshot(self):
        return SimpleNamespace(name="screen.png")

    def new_chat(self, key, name=None):
        return name or "Диалог 1", SimpleNamespace(url="https://chatgpt.local/c/new")

    def list_chats(self, key):
        return [("ABIE", True), ("Личное", False)]

    def add_current_chat(self, key, name):
        return SimpleNamespace(id="existing", url="https://chatgpt.local/c/existing")

    def select_chat(self, key, name):
        return name, SimpleNamespace(id="selected", url="https://chatgpt.local/c/selected")


@pytest.fixture
def settings(tmp_path):
    return Settings("token", "/brave", "/profile", tmp_path, "sqlite:///:memory:",
                    gpt_timeout=1, max_message_length=3900)


@pytest.mark.asyncio
async def test_message_flow_sends_waiting_then_edits_result(settings):
    bot, dispatcher, service = FakeBot(), FakeDispatcher(), FakeService("Ответ")
    handler = MaxBotHandler(settings, service, bot=bot, dispatcher=dispatcher)
    event = FakeEvent("Привет")
    await handler.on_message(event)
    assert event.message.answers == ["⏳ Жду ответ ChatGPT…"]
    assert service.calls == [("42", "Привет")]
    assert bot.edits == [("sent-1", "Ответ")]


@pytest.mark.asyncio
async def test_error_replaces_waiting_message(settings):
    bot, dispatcher = FakeBot(), FakeDispatcher()
    handler = MaxBotHandler(settings, FakeService(error=RuntimeError("boom")),
                            bot=bot, dispatcher=dispatcher)
    event = FakeEvent("сломайся")
    await handler.on_message(event)
    assert event.message.answers == ["⏳ Жду ответ ChatGPT…"]
    assert bot.edits == [("sent-1", "❌ Ошибка: RuntimeError: boom")]


@pytest.mark.asyncio
async def test_status_command_does_not_call_chatgpt(settings):
    bot, dispatcher, service = FakeBot(), FakeDispatcher(), FakeService()
    handler = MaxBotHandler(settings, service, bot=bot, dispatcher=dispatcher)
    event = FakeEvent("/status")
    await handler.on_message(event)
    assert event.message.answers == ["ChatGPT: ready"]
    assert service.calls == []


@pytest.mark.asyncio
async def test_long_answer_edits_first_chunk_and_sends_rest(settings):
    settings = Settings("token", "/brave", "/profile", settings.screenshot_dir,
                        "sqlite:///:memory:", gpt_timeout=1, max_message_length=5)
    bot, dispatcher = FakeBot(), FakeDispatcher()
    handler = MaxBotHandler(settings, FakeService("abcdefghij"),
                            bot=bot, dispatcher=dispatcher)
    event = FakeEvent("x")
    await handler.on_message(event)
    assert bot.edits[0] == ("sent-1", "abcde")
    assert event.message.answers == ["⏳ Жду ответ ChatGPT…", "fghij"]


@pytest.mark.asyncio
async def test_multiline_max_message_is_one_lossless_chatgpt_request(settings):
    bot, dispatcher, service = FakeBot(), FakeDispatcher(), FakeService("OK")
    handler = MaxBotHandler(settings, service, bot=bot, dispatcher=dispatcher)
    original = "  первая строка\nвторая строка\n\nтретья строка\n"
    event = FakeEvent(original)

    await handler.on_message(event)

    assert len(service.calls) == 1
    assert service.calls[0] == ("42", original)
    assert bot.edits == [("sent-1", "OK")]


@pytest.mark.asyncio
async def test_dialog_commands(settings):
    bot, dispatcher, service = FakeBot(), FakeDispatcher(), FakeService()
    handler = MaxBotHandler(settings, service, bot=bot, dispatcher=dispatcher)

    event = FakeEvent("НД Тесты ABIE")
    await handler.on_message(event)
    assert event.message.answers == ["Создан диалог «Тесты ABIE»."]

    event = FakeEvent("СД")
    await handler.on_message(event)
    assert event.message.answers == ["Диалоги:\n→ ABIE\n  Личное"]

    event = FakeEvent("ДД Старый чат")
    await handler.on_message(event)
    assert event.message.answers == ["Диалог «Старый чат» сохранён."]

    event = FakeEvent("ВД ABIE")
    await handler.on_message(event)
    assert event.message.answers == ["Выбран диалог «ABIE»."]
