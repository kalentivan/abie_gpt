from __future__ import annotations

import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

from abie_gpt.core.config import Settings
from abie_gpt.core.models import AssistantResponse, BrowserState, Conversation
from .selectors import ASSISTANT_MESSAGES, COMPOSERS, SEND_BUTTONS, STOP_BUTTONS


class ChatGPTHandler:
    """Owns all direct interaction with the ChatGPT browser UI."""

    CHATGPT_URL = "https://chatgpt.com/"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.driver = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self.driver:
                return
            self.driver = Driver(
                browser="chrome",
                binary_location=self.settings.brave_path,
                user_data_dir=self.settings.browser_profile,
                headless=False,
            )
            self.driver.get(self.CHATGPT_URL)
            self.ensure_ready()

    def close(self) -> None:
        with self._lock:
            if self.driver:
                self.driver.quit()
                self.driver = None

    def health(self) -> BrowserState:
        if not self.driver:
            return BrowserState.ERROR
        if self._visible(STOP_BUTTONS):
            return BrowserState.GENERATING
        if self._find_composer(1, required=False):
            return BrowserState.READY
        page = (self.driver.page_source or "").lower()
        if "log in" in page or "войти" in page:
            return BrowserState.LOGIN_REQUIRED
        return BrowserState.ERROR

    def ensure_ready(self) -> None:
        if not self.driver:
            raise RuntimeError("Browser is not started")
        state = self.health()
        if state == BrowserState.LOGIN_REQUIRED:
            raise RuntimeError("ChatGPT login required")
        if state != BrowserState.GENERATING:
            self._find_composer(30)

    def new_chat(self) -> Conversation:
        with self._lock:
            self.driver.get(self.CHATGPT_URL)
            self._find_composer(30)
            return self.current_chat()

    def current_chat(self) -> Conversation:
        url = self.driver.current_url
        parts = [part for part in urlparse(url).path.split("/") if part]
        chat_id = parts[1] if len(parts) >= 2 and parts[0] == "c" else None
        return Conversation(chat_id, self.driver.title, url, True)

    def open_chat(self, chat_id: str) -> Conversation:
        with self._lock:
            if not chat_id or "/" in chat_id:
                raise ValueError("Invalid conversation id")
            self.driver.get(f"{self.CHATGPT_URL}c/{chat_id}")
            self._find_composer(30)
            chat = self.current_chat()
            if chat.id != chat_id:
                raise RuntimeError("Requested conversation was not opened")
            return chat

    def send_and_wait(self, prompt: str) -> AssistantResponse:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt is empty")
        with self._lock:
            self.ensure_ready()
            before = len(self._assistant_messages())
            box = self._find_composer(30)
            box.click()
            box.send_keys(prompt)
            self._click_send(box)
            text, completed = self._wait_answer(before)
            return AssistantResponse(text, self.driver.current_url, completed)

    def stop_generation(self) -> bool:
        with self._lock:
            for selector in STOP_BUTTONS:
                for button in self.driver.find_elements("css selector", selector):
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        return True
            return False

    def screenshot(self) -> Path:
        with self._lock:
            path = self.settings.screenshot_dir / f"chatgpt-{int(time.time())}.png"
            self.driver.save_screenshot(str(path))
            return path

    def _assistant_messages(self):
        return self.driver.find_elements("css selector", ASSISTANT_MESSAGES)

    def _wait_answer(self, before: int) -> tuple[str, bool]:
        deadline = time.monotonic() + self.settings.gpt_timeout
        last, stable_since = "", None
        while time.monotonic() < deadline:
            messages = self._assistant_messages()
            if len(messages) > before:
                current = messages[-1].text.strip()
                if current != last and current:
                    last, stable_since = current, time.monotonic()
                elif last and stable_since and time.monotonic() - stable_since >= 1 and not self._visible(STOP_BUTTONS):
                    return last, True
            time.sleep(0.25)
        if last:
            return last, False
        raise TimeoutError("ChatGPT response timeout")

    def _click_send(self, box) -> None:
        for selector in SEND_BUTTONS:
            for button in self.driver.find_elements("css selector", selector):
                if button.is_displayed() and button.is_enabled():
                    button.click()
                    return
        box.send_keys(Keys.ENTER)

    def _find_composer(self, timeout: float, required: bool = True):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for selector in COMPOSERS:
                for element in self.driver.find_elements("css selector", selector):
                    if element.is_displayed() and element.is_enabled():
                        return element
            time.sleep(0.2)
        if required:
            raise RuntimeError("ChatGPT composer not found")
        return None

    def _visible(self, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                if any(x.is_displayed() for x in self.driver.find_elements("css selector", selector)):
                    return True
            except Exception:
                continue
        return False
