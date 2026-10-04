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
        active_dialog = None
        if saved:
            for dialog in self.database.list_named_dialogs(external_key):
                if ((saved.chatgpt_id and dialog.chatgpt_id == saved.chatgpt_id)
                        or dialog.chatgpt_url == saved.chatgpt_url):
                    active_dialog = dialog
                    break
        response = self.chatgpt.send_and_wait(text)
        current = self.chatgpt.current_chat()
        self.database.save_conversation(external_key, current.id, current.url)
        if active_dialog:
            self.database.touch_named_dialog(
                external_key, active_dialog.name, current.id, current.url
            )
        return response.text

    def new_chat(self, external_key: str, name: str | None = None):
        name = (name or "").strip() or self.database.next_dialog_name(external_key)
        if self.database.get_named_dialog(external_key, name):
            raise ValueError(f'Диалог с названием «{name}» уже существует')
        chat = self.chatgpt.new_chat()
        self.database.save_named_dialog(external_key, name, chat.id, chat.url)
        self.database.save_conversation(external_key, chat.id, chat.url)
        return name, chat

    def add_current_chat(self, external_key: str, name: str):
        name = name.strip()
        if not name:
            raise ValueError("Укажите название диалога")
        if self.database.get_named_dialog(external_key, name):
            raise ValueError(f'Диалог с названием «{name}» уже существует')
        chat = self.chatgpt.current_chat()
        if not chat.id:
            raise ValueError("Сейчас открыт новый пустой ChatGPT-диалог без conversation id")
        self.database.save_named_dialog(external_key, name, chat.id, chat.url)
        self.database.save_conversation(external_key, chat.id, chat.url)
        return chat

    def list_chats(self, external_key: str):
        active = self.database.get_conversation(external_key)
        active_id = active.chatgpt_id if active else None
        return [(row.name, bool(active_id and row.chatgpt_id == active_id))
                for row in self.database.list_named_dialogs(external_key)]

    def select_chat(self, external_key: str, name: str):
        row = self.database.get_named_dialog(external_key, name.strip())
        if row is None:
            raise ValueError(f'Диалог «{name.strip()}» не найден')
        if not row.chatgpt_id:
            current = self.chatgpt.current_chat()
            if current.url != row.chatgpt_url:
                raise ValueError("У этого диалога ещё нет conversation id; отправьте в него первое сообщение")
            chat = current
        else:
            chat = self.chatgpt.open_chat(row.chatgpt_id)
        self.database.touch_named_dialog(external_key, row.name, chat.id, chat.url)
        self.database.save_conversation(external_key, chat.id, chat.url)
        return row.name, chat

    def stop(self) -> bool:
        return self.chatgpt.stop_generation()

    def status(self) -> str:
        return self.chatgpt.health().value

    def screenshot(self):
        return self.chatgpt.screenshot()
