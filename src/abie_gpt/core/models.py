from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BrowserState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    GENERATING = "generating"
    LOGIN_REQUIRED = "login_required"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str | None
    title: str
    url: str
    active: bool = False


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    text: str
    conversation_url: str
    completed: bool
