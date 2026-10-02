from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .models import TelegramDialog, TelegramMessage

MessageCallback = Callable[[TelegramMessage], Awaitable[None] | None]


class TelegramPort(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def is_authorized(self) -> bool: ...
    async def send_code(self, phone: str) -> None: ...
    async def sign_in(self, phone: str, code: str, password: str | None = None) -> None: ...
    async def list_dialogs(self, limit: int = 100) -> list[TelegramDialog]: ...
    async def list_messages(self, dialog_id: int, limit: int = 100) -> list[TelegramMessage]: ...
    async def send_message(self, dialog_id: int, text: str) -> TelegramMessage: ...
    def subscribe(self, callback: MessageCallback) -> None: ...


class TelegramService:
    def __init__(self, client: TelegramPort):
        self.client = client

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def is_authorized(self) -> bool:
        return await self.client.is_authorized()

    async def send_code(self, phone: str) -> None:
        phone = phone.strip()
        if not phone:
            raise ValueError("Phone is required")
        await self.client.send_code(phone)

    async def sign_in(self, phone: str, code: str, password: str | None = None) -> None:
        if not code.strip():
            raise ValueError("Telegram code is required")
        await self.client.sign_in(phone.strip(), code.strip(), password)

    async def dialogs(self, limit: int = 100) -> list[TelegramDialog]:
        return await self.client.list_dialogs(limit)

    async def messages(self, dialog_id: int, limit: int = 100) -> list[TelegramMessage]:
        return await self.client.list_messages(dialog_id, limit)

    async def send(self, dialog_id: int, text: str) -> TelegramMessage:
        text = text.strip()
        if not text:
            raise ValueError("Message is empty")
        return await self.client.send_message(dialog_id, text)

    def subscribe(self, callback: MessageCallback) -> None:
        self.client.subscribe(callback)
