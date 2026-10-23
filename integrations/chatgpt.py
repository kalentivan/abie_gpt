import shutil
import time
from pathlib import Path

import requests

from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

from config import settings

BRAVE_PATH = settings.brave_path
BOT_PROFILE = str(settings.bot_profile)
SCREENSHOT_PATH = settings.screenshot_path.resolve()
GPT_TIMEOUT = settings.gpt_timeout
GPT_DOWNLOADS = settings.gpt_downloads.resolve()
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

    def _is_composer(self, element):
        """Never accept an editable node belonging to an assistant/user turn."""
        return bool(self.driver.execute_script(r"""
            const el = arguments[0];
            if (!el || !el.isConnected) return false;
            if (el.closest('[data-message-author-role], article[data-testid*="conversation-turn"]'))
                return false;
            if (el.closest('[data-testid*="writing-block"], [data-testid*="artifact"]'))
                return false;
            const explicitlyNamed = el.matches('#prompt-textarea, #mobile-composer-prompt');
            const inComposer = Boolean(el.closest(
                'form, [data-testid="composer"], [data-testid="composer-footer"], #composer-background'
            ));
            return explicitlyNamed || inComposer;
        """, element))

    def find_input_box(self, timeout=30):
        """Find the message composer, never the answer's editable writing block."""
        selectors = [
            "#prompt-textarea",
            "#mobile-composer-prompt",
            'form [contenteditable="true"][role="textbox"]',
            'form [contenteditable="true"]',
            'form textarea',
            '[data-testid="composer"] [contenteditable="true"]',
            '[data-testid="composer"] textarea',
        ]
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    for element in self.driver.find_elements("css selector", selector):
                        if (element.is_displayed() and element.is_enabled()
                                and self._is_composer(element)):
                            self.log(f"Composer: {selector}")
                            return element
                except Exception:
                    pass
            time.sleep(0.5)
        raise RuntimeError("Не найден настоящий composer ChatGPT (редактируемые блоки исключены)")

    def get_page_text(self):
        for selector in ("main", '[role="main"]', "body"):
            try:
                for element in self.driver.find_elements("css selector", selector):
                    if element.is_displayed():
                        value = element.text.strip()
                        if value:
                            return value
            except Exception:
                pass
        return ""

    def _assistant_turns(self):
        """Return assistant message elements, excluding prior user messages."""
        turns = self.driver.find_elements(
            "css selector", '[data-message-author-role="assistant"]'
        )
        if turns:
            return turns

        labels = self.driver.find_elements(
            "xpath", "//h4[normalize-space()='ChatGPT said:']"
        )
        result = []
        for label in labels:
            try:
                result.append(label.find_element("xpath", "./following-sibling::*[1]"))
            except Exception:
                pass
        return result

    def _read_assistant_turn(self, element):
        """Read visible answer text including nested editable writing-block content.

        Note: widgets rendered outside the message DOM may require a separate
        extraction strategy after inspecting their actual HTML.
        """
        return self.driver.execute_script(r"""
            const root = arguments[0];
            const clone = root.cloneNode(true);
            const ignored = 'button, [role="toolbar"], [aria-hidden="true"], script, style';
            clone.querySelectorAll(ignored).forEach(n => n.remove());
            for (const el of clone.querySelectorAll('textarea, input')) {
                const value = el.value || el.getAttribute('value') || '';
                if (value) el.replaceWith(document.createTextNode(value));
            }
            // innerText on the original captures visual layout, but some UI
            // components expose only their editable text. Preserve it if absent.
            let visible = root.innerText || '';
            for (const editor of root.querySelectorAll('[contenteditable="true"]')) {
                const t = (editor.innerText || editor.textContent || '').trim();
                if (t && !visible.includes(t)) visible += '\n' + t;
            }
            for (const field of root.querySelectorAll('textarea')) {
                const t = field.value?.trim();
                if (t && !visible.includes(t)) visible += '\n' + t;
            }
            return visible.trim();
        """, element)

    def get_assistant_text(self):
        try:
            turns = self._assistant_turns()
            if not turns:
                return None
            value = self._read_assistant_turn(turns[-1])
            return value or None
        except Exception as error:
            self.log(f"Не удалось прочитать assistant: {error}")
            return None

    @staticmethod
    def _normalize_newlines(text):
        return str(text).replace("\r\n", "\n").replace("\r", "\n")

    def _editor_value(self, input_box):
        """Get semantic text, not innerText's rendering-dependent blank lines."""
        return self.driver.execute_script(
            r"""
            const el = arguments[0];
            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                return el.value;
            }
            // ProseMirror (ChatGPT) stores lines in p/div blocks. innerText
            // can count both block edges and <br> as extra newlines.
            const isBlock = (node) => /^(P|DIV)$/.test(node.nodeName);
            const readInline = (node) => {
                if (node.nodeType === Node.TEXT_NODE) return node.nodeValue;
                if (node.nodeType !== Node.ELEMENT_NODE) return '';
                if (node.nodeName === 'BR') {
                    // ProseMirror's final placeholder BR is not user content.
                    if (node.classList.contains('ProseMirror-trailingBreak')) return '';
                    return '\n';
                }
                if (node.getAttribute('data-placeholder') !== null &&
                    !node.textContent) return '';
                let out = '';
                for (const child of node.childNodes) out += readInline(child);
                return out;
            };
            const blocks = [...el.childNodes].filter(n =>
                n.nodeType === Node.ELEMENT_NODE && isBlock(n)
            );
            if (blocks.length && blocks.length === [...el.childNodes].filter(n =>
                n.nodeType === Node.ELEMENT_NODE ||
                (n.nodeType === Node.TEXT_NODE && n.nodeValue.trim())
            ).length) {
                return blocks.map(readInline).join('\n');
            }
            return readInline(el);
            """,
            input_box,
        )

    def type_prompt(self, input_box, prompt):
        """Insert text only into the verified composer, preserving blank lines."""
        if not self._is_composer(input_box):
            raise RuntimeError("Отказ от ввода: элемент не является composer ChatGPT")
        prompt = self._normalize_newlines(prompt)
        input_box.click()
        if not self._is_composer(input_box):
            raise RuntimeError("Composer изменился после получения фокуса")
        input_box.send_keys(Keys.CONTROL, "a")
        input_box.send_keys(Keys.BACKSPACE)
        self.driver.execute_cdp_cmd("Input.insertText", {"text": prompt})
        time.sleep(0.15)
        actual = self._normalize_newlines(self._editor_value(input_box))
        self.log(f"Ожидалось в редакторе: {prompt!r}")
        self.log(f"Фактически в редакторе: {actual!r}")
        if actual != prompt:
            html = self.driver.execute_script("return arguments[0].innerHTML;", input_box)
            self.log(f"HTML редактора (до 1000 символов): {html[:1000]!r}")
            raise RuntimeError("Текст в composer не совпадает с исходным. Сообщение НЕ отправлено.")

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
        raise TimeoutError("Не найдена активная кнопка отправки")

    def upload_files(self, paths):
        paths = [Path(path).resolve() for path in paths]
        if not paths:
            return
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(f"Не найден файл для отправки: {path}")

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
            turns = self._assistant_turns()
            if not turns:
                return []
            return [
                url
                for link in turns[-1].find_elements("css selector", "a[href]")
                if (url := link.get_attribute("href"))
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
        try:
            response = session.get(url, timeout=120, stream=True, allow_redirects=True)
            try:
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
            finally:
                response.close()
        finally:
            session.close()

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
        self.log(f"Запрос: {str(prompt)[:200]!r}")
        self.log(f"URL до отправки: {self.driver.current_url}")
        before = self.get_page_text()
        self.log(f"Текст страницы до отправки: {len(before)} символов")
        previous_turn_count = len(self._assistant_turns())
        input_box = self.find_input_box()
        self.type_prompt(input_box, prompt)
        self.log("Текст введён")
        time.sleep(0.5)
        self.click_send(input_box)
        self.log("Запрос отправлен")
        answer = self._wait_answer(before, previous_turn_count)
        self.log(f"URL после ответа: {self.driver.current_url}")
        self.log(f"Получен ответ: {answer[:300]!r}")
        self.log("=" * 50)
        return answer

    def _wait_answer(self, before, previous_turn_count=0):
        deadline = time.time() + GPT_TIMEOUT
        last_answer = None
        last_log = 0
        self.log("Жду ответ ChatGPT...")
        while time.time() < deadline:
            try:
                turns = self._assistant_turns()
                answer = (
                    self._read_assistant_turn(turns[-1])
                    if len(turns) > previous_turn_count
                    else None
                )
                if answer and answer != last_answer:
                    self.log(f"Ответ: {len(answer)} символов | {answer[-150:]!r}")
                    last_answer = answer
                complete = self.driver.find_elements(
                    "xpath",
                    "//*[@role='status' and normalize-space()='Response complete']",
                )
                if last_answer and complete:
                    latest = self._assistant_turns()
                    if len(latest) > previous_turn_count:
                        last_answer = self._read_assistant_turn(latest[-1]) or last_answer
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
