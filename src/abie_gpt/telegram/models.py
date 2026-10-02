from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DialogKind(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"


@dataclass(frozen=True, slots=True)
class TelegramDialog:
    id: int
    title: str
    kind: DialogKind
    unread_count: int = 0
    last_message: str = ""
    last_message_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    id: int
    dialog_id: int
    text: str
    sender_name: str
    sent_at: datetime
    outgoing: bool = False
