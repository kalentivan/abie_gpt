import os
import shutil
import time
from pathlib import Path

import requests

from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

BRAVE_PATH = os.environ["BRAVE_PATH"]
BOT_PROFILE = os.environ["BOT_PROFILE"]
SCREENSHOT_PATH = Path(os.environ["SCREENSHOT_PATH"])
GPT_TIMEOUT = int(os.environ["GPT_TIMEOUT"])
GPT_DOWNLOADS = Path(os.getenv("GPT_DOWNLOADS", "runtime/gpt-downloads")).resolve()
GPT_DOWNLOADS.mkdir(parents=True, exist_ok=True)


class ChatGPTHandler:
    def __init__(self):
        self.driver = None

    def log(self, message):
        print(f"[GPT] {message}", flush=True)

    def start(self):
        self.log("Запускаю Brave...")
        self.log(f"Binary: {BRAVE_PATH}")
        self.log(f"Profile: {BOT_PROFILE}")

        self.driver = Driver(
            browser="chrome",
            binary_location=BRAVE_PATH,
            user_data_dir=BOT_PROFILE,
            headless=False,
        )

        self.log("Brave запущен")
        self.driver.get("https://chatgpt.com/")
        self.log(f"Страница открыта: {self.driver.current_url}")

        self.find_input_box()
        self.log("Поле ввода найдено")
        self.log("ChatGPT готов")

    def find_input_box(self, timeout=30):
        selectors = [
            "#prompt-textarea",
            "#mobile-composer-prompt",
            '[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
            "textarea",
        ]
        deadline = time.time() + timeout

        while time.time() < deadline:
            for selector in selectors:
                try:
                    for element in self.driver.find_elements("css selector", selector):
                        if element.is_displayed() and element.is_enabled():
                            self.log(f"Composer: {selector}")
                            return element
                except Exception:
                    pass
            time.sleep(0.5)

        raise RuntimeError("Не найдено поле ввода ChatGPT")

    def get_page_text(self):
        selectors = ["main", '[role="main"]', "body"]

        for selector in selectors:
            try:
                elements = self.driver.find_elements("css selector", selector)
                for element in elements:
                    if element.is_displayed():
                        text = element.text.strip()
                        if text:
                            return text
            except Exception:
                pass

        return ""

    def get_assistant_text(self):
        try:
            labels = self.driver.find_elements(
                "xpath",
                "//h4[normalize-space()='ChatGPT said:']",
            )

            if not labels:
                return None

            label = labels[-1]
            turn = label.find_element(
                "xpath",
                "./following-sibling::*[1]",
            )

            text = turn.text.strip()
            return text or None

        except Exception as error:
            self.log(f"Не удалось прочитать assistant: {error}")
            return None

    def click_send(self, input_box):
        selectors = [
            'button[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Отправ"]',
        ]

        for selector in selectors:
            try:
                for button in self.driver.find_elements("css selector", selector):
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        self.log(f"Нажата кнопка отправки: {selector}")
                        return
            except Exception as error:
                self.log(f"Ошибка проверки {selector}: {error}")

        self.log("Кнопка отправки не найдена, использую Enter")
        input_box.send_keys(Keys.ENTER)

    def upload_files(self, paths):
        paths = [Path(path).resolve() for path in paths]
        if not paths:
            return

        inputs = self.driver.find_elements("css selector", 'input[type="file"]')
        if not inputs:
            raise RuntimeError("Не найден input[type=file] ChatGPT")

        file_input = inputs[-1]
        file_input.send_keys("\n".join(str(path) for path in paths))
        self.log("Загружены файлы: " + ", ".join(path.name for path in paths))
        time.sleep(2)

    def _assistant_links(self):
        try:
            labels = self.driver.find_elements(
                "xpath",
                "//h4[normalize-space()='ChatGPT said:']",
            )
            if not labels:
                return []
            turn = labels[-1].find_element("xpath", "./following-sibling::*[1]")
            return [
                link.get_attribute("href")
                for link in turn.find_elements("css selector", "a[href]")
                if link.get_attribute("href")
            ]
        except Exception as error:
            self.log(f"Не удалось прочитать ссылки assistant: {error}")
            return []

    def _download_url(self, url):
        if not url.startswith(("http://", "https://")):
            return None

        session = requests.Session()
        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        response = session.get(url, timeout=120, stream=True, allow_redirects=True)
        response.raise_for_status()

        disposition = response.headers.get("content-disposition", "")
        content_type = response.headers.get("content-type", "").lower()
        if "attachment" not in disposition.lower() and "text/html" in content_type:
            return None

        name = None
        if "filename=" in disposition:
            name = disposition.split("filename=", 1)[1].strip().strip('"')
        if not name:
            name = Path(response.url.split("?", 1)[0]).name
        if not name:
            return None

        target = GPT_DOWNLOADS / Path(name).name
        with target.open("wb") as output:
            shutil.copyfileobj(response.raw, output)
        return target

    def download_assistant_files(self):
        result = []
        for url in self._assistant_links():
            try:
                path = self._download_url(url)
                if path and path.is_file():
                    result.append(path)
            except Exception as error:
                self.log(f"Не удалось скачать {url}: {error}")
        return result

    def send_with_files(self, prompt, paths=None):
        if paths:
            self.upload_files(paths)
        answer = self.send(prompt)
        return answer, self.download_assistant_files()

    def send(self, prompt):
        self.log("=" * 50)
        self.log(f"Запрос: {prompt[:200]!r}")
        self.log(f"URL до отправки: {self.driver.current_url}")

        before = self.get_page_text()
        self.log(f"Текст страницы до отправки: {len(before)} символов")

        input_box = self.find_input_box()
        input_box.click()
        input_box.send_keys(prompt)

        self.log("Текст введён")
        time.sleep(0.5)

        self.click_send(input_box)
        self.log("Запрос отправлен")

        answer = self._wait_answer(before)

        self.log(f"URL после ответа: {self.driver.current_url}")
        self.log(f"Получен ответ: {answer[:300]!r}")
        self.log("=" * 50)

        return answer

    def _wait_answer(self, before):
        deadline = time.time() + GPT_TIMEOUT
        last_answer = None
        last_log = 0

        self.log("Жду ответ ChatGPT...")

        while time.time() < deadline:
            try:
                answer = self.get_assistant_text()

                if answer and answer != last_answer:
                    self.log(
                        f"Ответ: {len(answer)} символов | "
                        f"{answer[-150:]!r}"
                    )
                    last_answer = answer

                complete = self.driver.find_elements(
                    "xpath",
                    "//*[@role='status' and normalize-space()='Response complete']",
                )

                if last_answer and complete:
                    self.log("ChatGPT сообщил: Response complete")
                    self.log(f"Финальный ответ: {last_answer!r}")
                    return last_answer

                if time.time() - last_log >= 5:
                    self.log(
                        f"Ожидание... "
                        f"answer={'YES' if last_answer else 'NO'}, "
                        f"complete={'YES' if complete else 'NO'}"
                    )
                    last_log = time.time()

            except Exception as error:
                self.log(f"Ошибка ожидания: {type(error).__name__}: {error}")

            time.sleep(0.3)

        if last_answer:
            self.log("Timeout, возвращаю последний прочитанный ответ")
            return last_answer

        raise TimeoutError("Не удалось получить ответ ChatGPT")

    def _extract_from_page(self, before, after):
        if after.startswith(before):
            result = after[len(before):].strip()
            if result:
                self.log(f"Изменение страницы: {result[:300]!r}")
                return result

        self.log("Не удалось безопасно выделить ответ из текста страницы")
        return None

    def new_dialog(self):
        self.log("Открываю новый диалог...")
        self.driver.get("https://chatgpt.com/")
        self.find_input_box()
        self.log(f"Новый диалог открыт: {self.driver.current_url}")

    def screenshot(self):
        self.driver.save_screenshot(str(SCREENSHOT_PATH))
        self.log(f"Скриншот сохранён: {SCREENSHOT_PATH}")
        return SCREENSHOT_PATH

    def close(self):
        if self.driver:
            self.log("Закрываю Brave...")
            self.driver.quit()
            self.driver = None
