from __future__ import annotations

from abie_gpt.chatgpt import ChatGPTHandler
from abie_gpt.storage import Database


class ChatService:
    """Application use-cases shared by transport adapters."""

    def __init__(self, chatgpt: ChatGPTHandler, database: Database):
        self.chatgpt = chatgpt
        self.database = database

    def ask(self, external_key: str, text: str) -> str:
        saved = self.database.get_conversation(external_key)
        if saved and saved.chatgpt_id:
            current = self.chatgpt.current_chat()
            if current.id != saved.chatgpt_id:
                self.chatgpt.open_chat(saved.chatgpt_id)
        response = self.chatgpt.send_and_wait(text)
        current = self.chatgpt.current_chat()
        self.database.save_conversation(external_key, current.id, current.url)
        return response.text

    def new_chat(self, external_key: str):
        chat = self.chatgpt.new_chat()
        self.database.save_conversation(external_key, chat.id, chat.url)
        return chat

    def stop(self) -> bool:
        return self.chatgpt.stop_generation()

    def status(self) -> str:
        return self.chatgpt.health().value

    def screenshot(self):
        return self.chatgpt.screenshot()
