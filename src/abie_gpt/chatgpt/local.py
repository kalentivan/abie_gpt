from __future__ import annotations

from collections import deque

from abie_gpt.core.models import AssistantResponse, BrowserState, Conversation


class LocalChatGPTHandler:
    """Deterministic Selenium replacement for unit and monolith tests."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = deque(responses or ["local response"])
        self.prompts: list[str] = []
        self.chat_id = "local-chat"
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.started = False

    def health(self) -> BrowserState:
        return BrowserState.READY if self.started else BrowserState.ERROR

    def current_chat(self) -> Conversation:
        return Conversation(self.chat_id, "Local test chat", f"https://chatgpt.local/c/{self.chat_id}", True)

    def open_chat(self, chat_id: str) -> Conversation:
        self.chat_id = chat_id
        return self.current_chat()

    def new_chat(self) -> Conversation:
        self.chat_id = "local-new-chat"
        return self.current_chat()

    def send_and_wait(self, prompt: str) -> AssistantResponse:
        self.prompts.append(prompt)
        text = self.responses.popleft() if self.responses else "TASK_COMPLETE"
        return AssistantResponse(text, self.current_chat().url, True)

    def stop_generation(self) -> bool:
        self.stopped = True
        return True
