from datetime import datetime, timezone

import pytest

from abie_gpt.telegram.local import FakeTelegramClient
from abie_gpt.telegram.models import DialogKind, TelegramMessage
from abie_gpt.telegram.service import TelegramService


@pytest.mark.asyncio
async def test_fake_client_lists_all_dialog_kinds():
    service = TelegramService(FakeTelegramClient())
    await service.connect()
    dialogs = await service.dialogs()
    assert {d.kind for d in dialogs} == {DialogKind.PRIVATE, DialogKind.GROUP, DialogKind.CHANNEL}


@pytest.mark.asyncio
async def test_send_message_is_persisted_in_fake_history():
    service = TelegramService(FakeTelegramClient())
    await service.connect()
    sent = await service.send(1, "Привет")
    assert sent.outgoing is True
    assert (await service.messages(1))[-1].text == "Привет"


@pytest.mark.asyncio
async def test_empty_message_is_rejected():
    service = TelegramService(FakeTelegramClient())
    with pytest.raises(ValueError):
        await service.send(1, "   ")


@pytest.mark.asyncio
async def test_new_message_subscription():
    client = FakeTelegramClient()
    service = TelegramService(client)
    received = []
    service.subscribe(received.append)
    message = TelegramMessage(99, 1, "Новое", "Иван", datetime.now(timezone.utc))
    await client.emit(message)
    assert received == [message]
