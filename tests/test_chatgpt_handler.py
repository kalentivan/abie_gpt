from pathlib import Path

import pytest

from abie_gpt.chatgpt.handler import ChatGPTHandler
from abie_gpt.core.config import Settings
from abie_gpt.core.models import BrowserState


class Element:
    def __init__(self, text="", displayed=True, enabled=True):
        self.text = text
        self.displayed = displayed
        self.enabled = enabled
        self.sent = []
        self.clicked = 0

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled

    def click(self):
        self.clicked += 1

    def send_keys(self, value):
        self.sent.append(value)


class DriverMock:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.current_url = "https://chatgpt.com/"
        self.title = "ChatGPT"
        self.page_source = ""
        self.quit_called = False
        self.urls = []
        self.composer = Element()
        self.send = Element()
        self.stop = None
        self.messages = []

    def get(self, url):
        self.urls.append(url)
        self.current_url = url

    def quit(self):
        self.quit_called = True

    def find_elements(self, by, selector):
        if selector == '[data-message-author-role="assistant"]':
            return self.messages
        if "stop" in selector:
            return [self.stop] if self.stop else []
        if "send" in selector or "composer-submit" in selector:
            return [self.send]
        if "prompt" in selector or "contenteditable" in selector:
            return [self.composer]
        return []

    def save_screenshot(self, path):
        Path(path).write_bytes(b"png")
        return True


@pytest.fixture
def settings(tmp_path):
    return Settings(
        max_bot_token="x", brave_path="/fake/brave", browser_profile="/fake/profile",
        screenshot_dir=tmp_path, database_url="sqlite:///:memory:", gpt_timeout=1,
        max_message_length=3900,
    )


def test_start_uses_injected_driver_without_real_selenium(settings):
    driver = DriverMock()
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.start()
    assert handler.driver is driver
    assert driver.urls == ["https://chatgpt.com/"]
    assert handler.health() == BrowserState.READY


def test_health_detects_login(settings):
    driver = DriverMock()
    driver.composer.displayed = False
    driver.page_source = "Log in to ChatGPT"
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.driver = driver
    assert handler.health() == BrowserState.LOGIN_REQUIRED


def test_open_chat_validates_id(settings):
    handler = ChatGPTHandler(settings, driver_factory=DriverMock)
    handler.driver = DriverMock()
    with pytest.raises(ValueError):
        handler.open_chat("../bad")


def test_stop_generation_clicks_stop(settings):
    driver = DriverMock()
    driver.stop = Element()
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.driver = driver
    assert handler.stop_generation() is True
    assert driver.stop.clicked == 1


def test_screenshot_uses_configured_directory(settings):
    driver = DriverMock()
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.driver = driver
    path = handler.screenshot()
    assert path.exists()


def test_close_quits_driver(settings):
    driver = DriverMock()
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.driver = driver
    handler.close()
    assert driver.quit_called is True
    assert handler.driver is None


def test_wait_answer_does_not_return_first_partial_chunk(settings, monkeypatch):
    settings.gpt_timeout = 20
    driver = DriverMock()
    handler = ChatGPTHandler(settings, driver_factory=lambda **kwargs: driver)
    handler.driver = driver

    clock = {"now": 0.0, "reads": 0}
    partial = Element("АХАХАХА")
    complete = Element("АХАХАХА. Канал связи живой, и весь ответ дошёл.")

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += seconds

    def assistant_messages():
        clock["reads"] += 1
        # Keep the first fragment unchanged long enough to trigger the old
        # one-second heuristic, then simulate the DOM continuing to stream.
        if clock["now"] < 2.0:
            return [partial]
        return [complete]

    monkeypatch.setattr("abie_gpt.chatgpt.handler.time.monotonic", monotonic)
    monkeypatch.setattr("abie_gpt.chatgpt.handler.time.sleep", sleep)
    monkeypatch.setattr(handler, "_assistant_messages", assistant_messages)
    monkeypatch.setattr(handler, "_visible", lambda selectors: False)

    text, completed = handler._wait_answer(0)

    assert completed is True
    assert text == complete.text
    assert clock["now"] >= 4.5
