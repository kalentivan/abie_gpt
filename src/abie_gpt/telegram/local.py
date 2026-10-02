from __future__ import annotations

from datetime import datetime, timezone

from .models import DialogKind, TelegramDialog, TelegramMessage


class FakeTelegramClient:
    def __init__(self):
        self.connected = False
        self.authorized = True
        self.callbacks = []
        self._dialogs = [
            TelegramDialog(1, "Иван", DialogKind.PRIVATE, last_message="Привет"),
            TelegramDialog(2, "ABIE Team", DialogKind.GROUP, unread_count=2, last_message="Тестируем"),
            TelegramDialog(3, "Новости", DialogKind.CHANNEL, last_message="Новый пост"),
        ]
        now = datetime.now(timezone.utc)
        self._messages = {
            1: [TelegramMessage(1, 1, "Привет", "Иван", now)],
            2: [TelegramMessage(2, 2, "Тестируем Telegram", "Команда", now)],
            3: [TelegramMessage(3, 3, "Новый пост", "Новости", now)],
        }
        self._next_id = 10

    async def connect(self): self.connected = True
    async def disconnect(self): self.connected = False
    async def is_authorized(self): return self.authorized
    async def send_code(self, phone): self.authorized = False
    async def sign_in(self, phone, code, password=None): self.authorized = True
    async def list_dialogs(self, limit=100): return self._dialogs[:limit]
    async def list_messages(self, dialog_id, limit=100): return self._messages.get(dialog_id, [])[-limit:]

    async def send_message(self, dialog_id, text):
        self._next_id += 1
        msg = TelegramMessage(self._next_id, dialog_id, text, "Вы", datetime.now(timezone.utc), True)
        self._messages.setdefault(dialog_id, []).append(msg)
        return msg

    def subscribe(self, callback): self.callbacks.append(callback)

    async def emit(self, message):
        for callback in self.callbacks:
            result = callback(message)
            if hasattr(result, "__await__"):
                await result
