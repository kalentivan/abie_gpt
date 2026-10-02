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

    def run_until_done(
        self,
        external_key: str,
        initial_prompt: str,
        continuation_prompt: str = (
            "Сразу продолжай работу с того места, где остановился. Работай максимально долго. "
            "Если задача полностью завершена, напиши СТОП АУДИТ."
        ),
    ) -> list[str]:
        state = self.database.get_autorun(external_key)
        if state is None or not state.enabled:
            self.database.set_autorun(external_key, True)
            state = self.database.get_autorun(external_key)

        responses: list[str] = []
        prompt = initial_prompt
        while state and state.enabled and state.iteration < state.max_iterations:
            response = self.ask(external_key, prompt)
            responses.append(response)
            iteration = self.database.advance_autorun(external_key)
            if state.stop_marker.casefold() in response.casefold():
                self.database.set_autorun(external_key, False)
                break
            state = self.database.get_autorun(external_key)
            if not state or not state.enabled or iteration >= state.max_iterations:
                break
            prompt = continuation_prompt
        return responses

    def set_autorun(self, external_key: str, enabled: bool) -> None:
        self.database.set_autorun(external_key, enabled)

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
