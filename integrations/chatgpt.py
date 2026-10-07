import shutil
import time
from datetime import datetime
from pathlib import Path

import requests

from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

from config import settings
from integrations.dialogs import DialogRegistry

BRAVE_PATH = settings.brave_path
BOT_PROFILE = str(settings.bot_profile)
SCREENSHOT_PATH = settings.screenshot_path.resolve()
GPT_TIMEOUT = settings.gpt_timeout
GPT_DOWNLOADS = settings.gpt_downloads.resolve()
GPT_DOWNLOADS.mkdir(parents=True, exist_ok=True)
GPT_DIALOGS = settings.gpt_dialogs.resolve()


class ChatGPTHandler:
    def __init__(self):
        self.driver = None
        self.dialogs = DialogRegistry(GPT_DIALOGS)

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
        active = self.dialogs.active()
        start_url = active["url"] if active else "https://chatgpt.com/"
        self.driver.get(start_url)
        self.log(f"Страница открыта: {self.driver.current_url}")
        if active:
            self.log(f"Восстановлен диалог: {active['title']}")

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

    def click_send(self, input_box, timeout=30):
        selectors = [
            'button[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Отправ"]',
        ]
        deadline = time.time() + timeout
        last_log = 0

        while time.time() < deadline:
            for selector in selectors:
                try:
                    for button in self.driver.find_elements("css selector", selector):
                        if button.is_displayed() and button.is_enabled():
                            try:
                                button.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", button)
                            self.log(f"Нажата кнопка отправки: {selector}")
                            return
                except Exception as error:
                    self.log(f"Ошибка проверки {selector}: {error}")

            if time.time() - last_log >= 3:
                self.log("Жду активную кнопку отправки...")
                last_log = time.time()
            time.sleep(0.25)

        self.log("Активная кнопка отправки не появилась, использую Enter")
        input_box = self.find_input_box()
        input_box.send_keys(Keys.ENTER)

    def upload_files(self, paths):
        paths = [Path(path).resolve() for path in paths]
        if not paths:
            return

        inputs = self.driver.find_elements("css selector", 'input[type="file"]')
        if not inputs:
            raise RuntimeError("Не найден input[type=file] ChatGPT")

        payload = "\n".join(str(path) for path in paths)
        errors = []
        for file_input in reversed(inputs):
            try:
                self.driver.execute_script(
                    "arguments[0].style.display='block';"
                    "arguments[0].style.visibility='visible';"
                    "arguments[0].removeAttribute('hidden');",
                    file_input,
                )
                file_input.send_keys(payload)
                self.log("Файлы переданы в composer: " + ", ".join(path.name for path in paths))
                self._wait_upload_ready(paths)
                return
            except Exception as error:
                errors.append(f"{type(error).__name__}: {error}")
                self.log(f"Upload input не подошёл: {errors[-1]}")

        raise RuntimeError(
            "Не удалось загрузить файл в ChatGPT: " + " | ".join(errors[-3:])
        )

    def _wait_upload_ready(self, paths, timeout=600):
        deadline = time.time() + timeout
        names = [path.name for path in paths]
        last_log = 0
        attachment_seen = False

        while time.time() < deadline:
            page = self.get_page_text()
            names_visible = all(name in page for name in names)
            attachment_seen = attachment_seen or names_visible
            send_ready = False

            for selector in (
                'button[data-testid="send-button"]',
                'button[aria-label="Send prompt"]',
                'button[aria-label*="Send"]',
                'button[aria-label*="Отправ"]',
            ):
                try:
                    if any(
                        button.is_displayed() and button.is_enabled()
                        for button in self.driver.find_elements("css selector", selector)
                    ):
                        send_ready = True
                        break
                except Exception:
                    pass

            # ChatGPT may remove the attachment filename from main.innerText
            # after processing it. Once the attachment was observed, an enabled
            # Send button is the reliable signal that the composer is ready.
            if attachment_seen and send_ready:
                self.log("Вложение обработано, кнопка отправки активна")
                return

            if time.time() - last_log >= 3:
                self.log(
                    f"Жду загрузку вложения... "
                    f"file={'YES' if names_visible else 'NO'}, "
                    f"seen={'YES' if attachment_seen else 'NO'}, "
                    f"send={'YES' if send_ready else 'NO'}"
                )
                last_log = time.time()
            time.sleep(0.3)

        raise TimeoutError("ChatGPT не подготовил вложение к отправке за 10 минут")

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
        self.dialogs.touch_active(self.driver.current_url)
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

    def _dialog_title(self, requested=None):
        requested = (requested or "").strip()
        base = requested or datetime.now().strftime("Диалог %Y-%m-%d %H:%M")
        existing = {item["title"].casefold() for item in self.dialogs.list()}
        if base.casefold() not in existing:
            return base
        index = 2
        while f"{base} ({index})".casefold() in existing:
            index += 1
        return f"{base} ({index})"

    def new_dialog(self, title=None):
        title = self._dialog_title(title)
        self.log(f"Создаю новый диалог: {title}")
        self.driver.get("https://chatgpt.com/")
        self.find_input_box()

        # ChatGPT assigns /c/<id> only after the first message. Send a harmless
        # seed automatically so the conversation can be persisted immediately.
        self.send("Привет")
        url = self.driver.current_url
        item = self.dialogs.remember(title, url)
        self.log(f"Новый диалог сохранён: {title} -> {url}")
        return item

    def list_dialogs(self):
        return self.dialogs.list()

    def switch_dialog(self, selector):
        item = self.dialogs.select(selector)
        self.log(f"Переключаю диалог: {item['title']} -> {item['url']}")
        self.driver.get(item["url"])
        self.find_input_box()
        self.log(f"Диалог открыт: {item['title']}")
        return item

    def screenshot(self):
        self.driver.save_screenshot(str(SCREENSHOT_PATH))
        self.log(f"Скриншот сохранён: {SCREENSHOT_PATH}")
        return SCREENSHOT_PATH

    def close(self):
        if self.driver:
            self.log("Закрываю Brave...")
            self.driver.quit()
            self.driver = None
