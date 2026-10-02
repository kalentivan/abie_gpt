from __future__ import annotations

from abie_gpt.chatgpt import ChatGPTHandler


class ChatService:
    """Application use-cases shared by transport adapters."""

    def __init__(self, chatgpt: ChatGPTHandler):
        self.chatgpt = chatgpt

    def ask(self, text: str) -> str:
        return self.chatgpt.send_and_wait(text).text

    def new_chat(self):
        return self.chatgpt.new_chat()

    def stop(self) -> bool:
        return self.chatgpt.stop_generation()

    def status(self) -> str:
        return self.chatgpt.health().value

    def screenshot(self):
        return self.chatgpt.screenshot()
