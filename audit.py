import time
from pathlib import Path
from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

from config import settings

BRAVE_PATH = settings.brave_path
BOT_PROFILE = str(settings.bot_profile)

CHECK_INTERVAL = 300
CHATGPT_URL = "https://chatgpt.com/"

START_PROMPT = Path("АУДИТ_СТАРТ.md").read_text(encoding="utf-8")
CONTINUE_PROMPT = Path("АУДИТ_ПРОДОЛЖЕНИЕ.md").read_text(encoding="utf-8")
FINAL_PROMPT = Path("АУДИТ_ФИНАЛ.md").read_text(encoding="utf-8")

STOP = "СТОП АУДИТ"
WAIT = "АУДИТ ОСТАНОВЛЕН ДО СОГЛАСОВАНИЯ"

MICROSERVICES = [
    "api",
    "tg",
    "llm",
    "embedding",
    "frontend",
    "documents",
    "gateway",
    "studwork",
    "human",
    "summary",
    "assessor",
    "pricing",
    "selector",
    "bid",
    "revision-diff",
    "execution-evaluator",
    "solver",
    "prompts",
    "planner",
    "analytics",
    "monitoring",
    "watch-dog",
    "workflow",
    "metrics",
    "codex-worker",
    "k8n"
]


class AuditRunner:
    def __init__(self):
        self.driver = None
        self.tabs = {}

    def log(self, message):
        print(f"[AUDIT] {message}", flush=True)

    def start(self):
        self.driver = Driver(
            browser="chrome",
            binary_location=BRAVE_PATH,
            user_data_dir=BOT_PROFILE,
            headless=False,
        )
        self.driver.get(CHATGPT_URL)
        self.find_input_box()
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
                            return element
                except Exception:
                    pass
            time.sleep(0.5)
        raise RuntimeError("Не найдено поле ввода ChatGPT")

    def send(self, text):
        box = self.find_input_box()
        box.click()
        box.send_keys(text)
        time.sleep(0.5)

        for selector in [
            'button[data-testid="send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Отправ"]',
        ]:
            try:
                for button in self.driver.find_elements("css selector", selector):
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        return
            except Exception:
                pass

        box.send_keys(Keys.ENTER)

    def get_last_answer(self):
        try:
            messages = self.driver.find_elements(
                "css selector",
                '[data-message-author-role="assistant"]',
            )
            if messages:
                text = messages[-1].text.strip()
                return text or None
        except Exception:
            pass

        try:
            labels = self.driver.find_elements(
                "xpath",
                "//h4[normalize-space()='ChatGPT said:']",
            )
            if labels:
                turn = labels[-1].find_element(
                    "xpath", "./following-sibling::*[1]"
                )
                return turn.text.strip() or None
        except Exception:
            pass

        return None

    def is_generating(self):
        selectors = [
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop"]',
            'button[aria-label*="Останов"]',
        ]
        for selector in selectors:
            try:
                for button in self.driver.find_elements("css selector", selector):
                    if button.is_displayed():
                        return True
            except Exception:
                pass
        return False

    def open_audits(self):
        first = True

        for service in MICROSERVICES:
            if not first:
                self.driver.execute_script("window.open('https://chatgpt.com/', '_blank');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.find_input_box()
            first = False

            self.send(START_PROMPT.replace("{MICROSERVICE}", service))
            self.tabs[service] = self.driver.current_window_handle
            self.log(f"{service}: аудит запущен")
            time.sleep(2)

    def run(self):
        while self.tabs:
            self.log(f"Проверяю {len(self.tabs)} активных аудитов")

            for service, handle in list(self.tabs.items()):
                try:
                    self.driver.switch_to.window(handle)

                    if self.is_generating():
                        self.log(f"{service}: ещё работает")
                        continue

                    answer = self.get_last_answer()
                    if not answer:
                        self.log(f"{service}: ответа пока нет")
                        continue

                    answer_upper = answer.upper()

                    if WAIT in answer_upper:
                        self.log(f"{service}: ОСТАНОВЛЕН ДО СОГЛАСОВАНИЯ")
                        del self.tabs[service]

                    elif STOP in answer_upper:
                        self.log(f"{service}: СТОП АУДИТ -> отправляю финал")
                        self.send(FINAL_PROMPT.replace("{MICROSERVICE}", service))
                        del self.tabs[service]

                    else:
                        self.log(f"{service}: продолжаю")
                        self.send(CONTINUE_PROMPT.replace("{MICROSERVICE}", service))

                except Exception as error:
                    self.log(f"{service}: ошибка: {type(error).__name__}: {error}")

            if self.tabs:
                self.log(f"Следующий обход через {CHECK_INTERVAL // 60} минут")
                time.sleep(CHECK_INTERVAL)

        self.log("Все аудиты завершены или остановлены")


if __name__ == "__main__":
    runner = AuditRunner()
    runner.start()
    runner.open_audits()
    runner.run()