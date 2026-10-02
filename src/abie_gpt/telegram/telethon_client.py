from __future__ import annotations

import inspect
import logging
from pathlib import Path

from .models import DialogKind, TelegramDialog, TelegramMessage

logger = logging.getLogger(__name__)


class TelethonTelegramClient:
    def __init__(self, api_id: int, api_hash: str, session: Path):
        if not api_id or not api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
        self.api_id, self.api_hash, self.session = api_id, api_hash, session
        self.client = None
        self.callbacks = []

    def _ensure_client(self):
        if self.client is None:
            try:
                from telethon import TelegramClient, events
            except ImportError as exc:
                raise RuntimeError("Telethon is not installed. Install the 'telegram' extra.") from exc
            self.session.parent.mkdir(parents=True, exist_ok=True)
            self.client = TelegramClient(str(self.session), self.api_id, self.api_hash)

            @self.client.on(events.NewMessage)
            async def on_message(event):
                msg = await self._map_message(event.message)
                for callback in tuple(self.callbacks):
                    result = callback(msg)
                    if inspect.isawaitable(result):
                        await result
        return self.client

    async def connect(self):
        await self._ensure_client().connect()
        logger.info("Telegram connected")

    async def disconnect(self):
        if self.client is not None:
            await self.client.disconnect()
        logger.info("Telegram disconnected")

    async def is_authorized(self):
        return await self._ensure_client().is_user_authorized()

    async def send_code(self, phone):
        await self._ensure_client().send_code_request(phone)

    async def sign_in(self, phone, code, password=None):
        from telethon.errors import SessionPasswordNeededError
        try:
            await self._ensure_client().sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            if not password:
                raise
            await self.client.sign_in(password=password)

    async def list_dialogs(self, limit=100):
        result = []
        async for dialog in self._ensure_client().iter_dialogs(limit=limit):
            entity = dialog.entity
            kind = DialogKind.PRIVATE
            if getattr(entity, "broadcast", False):
                kind = DialogKind.CHANNEL
            elif getattr(entity, "megagroup", False) or getattr(entity, "participants_count", None) is not None:
                kind = DialogKind.GROUP
            last = dialog.message
            result.append(TelegramDialog(
                id=int(dialog.id), title=dialog.name or str(dialog.id), kind=kind,
                unread_count=int(dialog.unread_count or 0),
                last_message=(getattr(last, "message", None) or "")[:200],
                last_message_at=getattr(last, "date", None),
            ))
        return result

    async def list_messages(self, dialog_id, limit=100):
        messages = await self._ensure_client().get_messages(dialog_id, limit=limit)
        mapped = [await self._map_message(m, dialog_id) for m in messages]
        return list(reversed(mapped))

    async def send_message(self, dialog_id, text):
        message = await self._ensure_client().send_message(dialog_id, text)
        return await self._map_message(message, dialog_id)

    def subscribe(self, callback):
        self.callbacks.append(callback)

    async def _map_message(self, message, dialog_id=None):
        sender = await message.get_sender()
        sender_name = (
            getattr(sender, "title", None)
            or " ".join(x for x in (getattr(sender, "first_name", None), getattr(sender, "last_name", None)) if x)
            or getattr(sender, "username", None)
            or ("Вы" if getattr(message, "out", False) else "Telegram")
        )
        peer_id = dialog_id if dialog_id is not None else getattr(message, "chat_id", 0)
        return TelegramMessage(
            id=int(message.id), dialog_id=int(peer_id or 0),
            text=getattr(message, "message", None) or "",
            sender_name=sender_name, sent_at=message.date,
            outgoing=bool(getattr(message, "out", False)),
        )
